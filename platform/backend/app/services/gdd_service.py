"""
GDD (Growing Degree Day) service — v1 / MVP.

Design (scoped down from a fuller per-plant-per-zone pipeline):
  * Daily GDD is computed per chamber (not per rack/zone) from the
    chamber's aggregated env_observations. Plants in the same
    chamber share that day's contribution.
  * Per-plant cumulative GDD walks plant_positions phases, looking
    up the daily contribution from whichever chamber the plant was in
    on each day.
  * An anchor chamber (default G120) defines GDD=0 for every plant.
    Days before the plant entered the anchor chamber yield negative
    GDD; days after yield positive GDD. This makes cross-plant
    comparisons align on a biologically meaningful event rather than
    on calendar sowing date.
  * All heavy dicts (chamber daily GDD, per-plant aligned series) are
    kept in process memory for the duration of a request. Caching
    across requests is deferred — the working set is small (≤ ~4
    chambers × ~400 days = 1.6k rows + ~1.3k plants × ~60 days).

Bilinear response function (plant-physiology standard):
    T_eff = min(max(T_mean, T_base), T_opt)
    daily_GDD = max(0, T_eff - T_base) * scale
  where scale ramps down linearly from 1.0 at T_opt to 0.0 at T_upper
  for supra-optimal days (T_mean > T_opt).

  Defaults: T_base=5, T_opt=25, T_upper=35 °C (per project memory).

A standalone verify_gdd_r_python.py against an R ground-truth
implementation is a manuscript-stage follow-up; for UI MVP we just
need the axis to be self-consistent.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import logging
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.phenotype import (
    EnvironmentObservation,
    GrowthChamber,
    Plant,
    PlantChamberHistory,
    RaspiObservation,
    Sensor,
)

logger = logging.getLogger(__name__)

# Bilinear params — matches the R pipeline defaults documented in
# project_manuscript_alignment_phase1.md.
T_BASE = 5.0
T_OPT = 25.0
T_UPPER = 35.0

DEFAULT_ANCHOR_CHAMBER = "G120"


def bilinear_gdd(t_mean: Optional[float]) -> float:
    """Return the daily GDD contribution for a mean temperature in °C.

    * T_mean < T_base → 0
    * T_base ≤ T_mean ≤ T_opt → T_mean - T_base
    * T_opt < T_mean < T_upper → linear ramp from (T_opt - T_base) → 0
    * T_mean ≥ T_upper → 0

    None input returns 0 (missing day contributes nothing).
    """
    if t_mean is None:
        return 0.0
    if t_mean < T_BASE:
        return 0.0
    if t_mean <= T_OPT:
        return float(t_mean - T_BASE)
    if t_mean >= T_UPPER:
        return 0.0
    # Supra-optimal: linear decay from (T_opt - T_base) down to 0.
    max_contrib = T_OPT - T_BASE
    decay = (T_UPPER - t_mean) / (T_UPPER - T_OPT)
    return float(max_contrib * decay)


class GDDService:
    def __init__(self, db: Session):
        self.db = db
        self._chamber_daily_cache: Dict[int, Dict[date, float]] = {}
        self._chamber_hourly_cache: Dict[int, Dict[datetime, float]] = {}
        self._chamber_coverage_cache: Dict[int, Set[date]] = {}
        self._chamber_id_by_code: Optional[Dict[str, int]] = None
        # Per-plant caches populated by _warmup_plants. The single-plant
        # accessors (_plant_phases, _plant_sowing_date,
        # compute_pre_g120_gdd_for_plant) consult these first and fall
        # back to per-plant queries on a miss, so external callers that
        # never invoke the bulk variants still work — they're just slow.
        self._plant_phases_cache: Dict[int, List[Tuple[int, str, date, Optional[date]]]] = {}
        self._sowing_cache: Dict[int, Optional[date]] = {}
        self._g120_entry_cache: Dict[int, Optional[date]] = {}
        self._parent_id_cache: Dict[int, Optional[int]] = {}
        # Populated by compute_plant_gdd_by_date when gaps interrupt the walk.
        self.last_gap_days: Set[date] = set()

    # ------------------------------------------------------------------
    # Bulk pre-loader — collapses N+1 plant queries into ~4 round trips.
    # ------------------------------------------------------------------

    def _warmup_plants(
        self,
        plant_ids: List[int],
        anchor_chamber_id: Optional[int],
    ) -> None:
        """Populate per-plant caches for the given individuals (and their
        parents, since pre-G120 GDD walks parent phases). Idempotent: only
        plants not already in cache are queried, so calling this twice in
        the same request (once for compute_plants_gdd_by_das, once for
        compute_pre_g120_gdd_for_plants) does not duplicate work.
        """
        if not plant_ids:
            return
        plant_set = set(plant_ids)

        # 1) parent_id per individual — also reveals which parent ids we
        # need phases for. Plants with no entry get None cached so we don't
        # re-query.
        missing = plant_set - self._parent_id_cache.keys()
        if missing:
            rows = (
                self.db.query(Plant.id, Plant.parent_plant_id)
                .filter(Plant.id.in_(missing))
                .all()
            )
            for pid in missing:
                self._parent_id_cache[pid] = None
            for r in rows:
                self._parent_id_cache[r.id] = r.parent_plant_id

        parent_ids = {
            self._parent_id_cache[pid]
            for pid in plant_set
            if self._parent_id_cache.get(pid) is not None
        }
        all_ids = plant_set | parent_ids

        # 2) phases for individuals AND parents in one query.
        missing = all_ids - self._plant_phases_cache.keys()
        if missing:
            for pid in missing:
                self._plant_phases_cache[pid] = []
            rows = (
                self.db.query(
                    PlantChamberHistory.plant_id,
                    PlantChamberHistory.chamber_id,
                    GrowthChamber.chamber_code,
                    PlantChamberHistory.entry_date,
                    PlantChamberHistory.exit_date,
                )
                .join(GrowthChamber, GrowthChamber.id == PlantChamberHistory.chamber_id)
                .filter(PlantChamberHistory.plant_id.in_(missing))
                .order_by(PlantChamberHistory.plant_id, PlantChamberHistory.entry_date)
                .all()
            )
            for r in rows:
                self._plant_phases_cache[r.plant_id].append(
                    (r.chamber_id, r.chamber_code, r.entry_date, r.exit_date)
                )

        # 3) earliest anchor-chamber entry per individual (None if never entered).
        if anchor_chamber_id is not None:
            missing = plant_set - self._g120_entry_cache.keys()
            if missing:
                for pid in missing:
                    self._g120_entry_cache[pid] = None
                rows = (
                    self.db.query(
                        PlantChamberHistory.plant_id,
                        func.min(PlantChamberHistory.entry_date).label("entry_date"),
                    )
                    .filter(PlantChamberHistory.plant_id.in_(missing))
                    .filter(PlantChamberHistory.chamber_id == anchor_chamber_id)
                    .group_by(PlantChamberHistory.plant_id)
                    .all()
                )
                for r in rows:
                    self._g120_entry_cache[r.plant_id] = r.entry_date

        # 4) sowing date per individual — earliest raspi obs with das set,
        # then sowing = ts.date() - das. DISTINCT ON keeps one row per plant.
        missing = plant_set - self._sowing_cache.keys()
        if missing:
            for pid in missing:
                self._sowing_cache[pid] = None
            rows = (
                self.db.query(
                    RaspiObservation.plant_id,
                    RaspiObservation.observation_timestamp,
                    RaspiObservation.day_after_sewing,
                )
                .filter(RaspiObservation.plant_id.in_(missing))
                .filter(RaspiObservation.day_after_sewing.isnot(None))
                .distinct(RaspiObservation.plant_id)
                .order_by(
                    RaspiObservation.plant_id,
                    RaspiObservation.observation_timestamp,
                )
                .all()
            )
            for r in rows:
                self._sowing_cache[r.plant_id] = (
                    r.observation_timestamp.date() - timedelta(days=int(r.day_after_sewing))
                )

    # ------------------------------------------------------------------
    # Chamber-level daily GDD
    # ------------------------------------------------------------------

    def _chamber_id_map(self) -> Dict[str, int]:
        if self._chamber_id_by_code is None:
            self._chamber_id_by_code = {
                c.chamber_code: c.id
                for c in self.db.query(GrowthChamber).all()
            }
        return self._chamber_id_by_code

    def get_chamber_daily_gdd(self, chamber_id: int) -> Dict[date, float]:
        """Return {date: daily_gdd} for every day with sensor data in this chamber.

        **Hourly-accumulative** method: for each hour in the chamber, take
        the mean temperature across all its sensors, apply the bilinear
        response, and add ``bilinear(T_h) / 24`` to that day's running
        total. This properly attenuates diurnal swings that a pure
        daily-mean calculation would hide — a day oscillating between
        15°C and 35°C has mean 25°C (appears optimal) but the actual
        integrated contribution is substantially lower because the
        35°C hours sit at the ceiling and contribute nothing.

        Days with partial sensor coverage are scaled only by the hours
        we actually observed (i.e. missing hours contribute 0, matching
        the env-data-gap semantics already used elsewhere).
        """
        if chamber_id in self._chamber_daily_cache:
            return self._chamber_daily_cache[chamber_id]

        hourly = self.get_chamber_hourly_gdd(chamber_id)
        daily: Dict[date, float] = {}
        coverage: Set[date] = set()
        for h, contrib in hourly.items():
            d = h.date()
            daily[d] = daily.get(d, 0.0) + contrib
            coverage.add(d)

        self._chamber_daily_cache[chamber_id] = daily
        self._chamber_coverage_cache[chamber_id] = coverage
        return daily

    def get_chamber_hourly_gdd(self, chamber_id: int) -> Dict[datetime, float]:
        """Return {hour: bilinear(T_hour) / 24} for this chamber.

        The hour *is* the unit of this model, so it is also the finest grain at
        which cumulative GDD is defined — which is what lets a per-frame series be
        plotted against thermal time instead of collapsing to one point per day.
        The daily view above is the sum of these, so the two can never disagree.
        """
        if chamber_id in self._chamber_hourly_cache:
            return self._chamber_hourly_cache[chamber_id]

        # Hourly mean temperature across all sensors in the chamber.
        hour = func.date_trunc("hour", EnvironmentObservation.observation_timestamp)
        rows = (
            self.db.query(
                hour.label("h"),
                func.avg(EnvironmentObservation.temperature_celsius).label("t_mean"),
            )
            .join(Sensor, Sensor.id == EnvironmentObservation.sensor_id)
            .filter(Sensor.chamber_id == chamber_id)
            .filter(EnvironmentObservation.temperature_celsius.isnot(None))
            .group_by(hour)
            .order_by(hour)
            .all()
        )
        hourly: Dict[datetime, float] = {}
        for r in rows:
            if r.h is None or r.t_mean is None:
                continue
            # 1/24 share for each hour so that a fully-covered day sums to
            # the integrated bilinear response of that hour's temperatures.
            hourly[r.h] = bilinear_gdd(float(r.t_mean)) / 24.0
        self._chamber_hourly_cache[chamber_id] = hourly
        return hourly

    def get_chamber_coverage_days(self, chamber_id: int) -> Set[date]:
        """Return the set of days the chamber has ≥1 hourly env observation.

        Coverage is a stronger signal than "daily_gdd has this key" because
        a day with all-below-base temperatures would have daily_gdd=0 but
        still be covered. Callers distinguish "covered + zero contribution"
        from "no env data at all" (env gap).
        """
        if chamber_id not in self._chamber_coverage_cache:
            # Populate both caches in one shot.
            self.get_chamber_daily_gdd(chamber_id)
        return self._chamber_coverage_cache.get(chamber_id, set())

    # ------------------------------------------------------------------
    # Per-plant phase walk + cumulative GDD anchored to G120 entry
    # ------------------------------------------------------------------

    def _plant_phases(self, plant_id: int) -> List[Tuple[int, str, date, Optional[date]]]:
        """Return a plant's phase list, ordered by entry_date.
        Each row: (chamber_id, chamber_code, entry_date, exit_date).
        """
        if plant_id in self._plant_phases_cache:
            return self._plant_phases_cache[plant_id]
        rows = (
            self.db.query(
                PlantChamberHistory.chamber_id,
                GrowthChamber.chamber_code,
                PlantChamberHistory.entry_date,
                PlantChamberHistory.exit_date,
            )
            .join(GrowthChamber, GrowthChamber.id == PlantChamberHistory.chamber_id)
            .filter(PlantChamberHistory.plant_id == plant_id)
            .order_by(PlantChamberHistory.entry_date)
            .all()
        )
        result = [(r.chamber_id, r.chamber_code, r.entry_date, r.exit_date) for r in rows]
        self._plant_phases_cache[plant_id] = result
        return result

    def compute_plant_gdd_by_date(
        self,
        plant_id: int,
        anchor_chamber_code: str = DEFAULT_ANCHOR_CHAMBER,
    ) -> Dict[date, Optional[float]]:
        """Return {date: gdd_aligned | None} for this plant.

        - GDD=0 at the plant's first observed day in the anchor chamber.
        - Positive afterwards (cumulative over the plant's chamber phases).
        - Negative before (same cumulative scheme, just shifted so anchor=0).
        - Plants that never entered the anchor chamber fall back to their
          earliest phase entry as the zero point (so all values ≥ 0).
        - **Gap handling:** when the walk hits a day on which the plant's
          current-phase chamber has no env observations at all, cumulative
          becomes ``None`` for that day and every subsequent day in the
          output (the integral is irrecoverably biased once we skip any
          day). Days whose chamber is covered but whose bilinear
          contribution is legitimately 0 (e.g. T < T_base) still get a
          real 0 — covered-zero and uncovered are different signals.

        Side effect: populates ``self.last_gap_days`` with the covered-less
        days that triggered gap mode for this plant, so callers can report
        the env-gap window.

        Empty dict if the plant has no phases, no chamber env data, or an
        unresolvable anchor chamber.
        """
        self.last_gap_days = set()
        phases = self._plant_phases(plant_id)
        if not phases:
            return {}

        # 1. Build the raw cumulative curve from the plant's earliest entry.
        #    Walk day-by-day, looking up each day's contribution from the
        #    chamber the plant was in that day.
        first_entry = min(p[2] for p in phases if p[2])
        last_exit = max(
            (p[3] or p[2]) for p in phases if (p[3] or p[2]) is not None
        )
        if last_exit is None or first_entry is None:
            return {}

        # Merge the plant's phases into a [(start, end, chamber_id)] list.
        segments: List[Tuple[date, date, int]] = []
        for chamber_id, _code, entry, exit_ in phases:
            if entry is None:
                continue
            end = exit_ or last_exit
            segments.append((entry, end, chamber_id))

        cumulative: Dict[date, Optional[float]] = {}
        running: Optional[float] = 0.0
        cursor = first_entry
        day = timedelta(days=1)
        # Iterate day-by-day up to last_exit. Each day, find the segment it
        # falls in (phases shouldn't overlap in practice).
        while cursor <= last_exit:
            current_cid: Optional[int] = None
            for seg_start, seg_end, cid in segments:
                if seg_start <= cursor <= seg_end:
                    current_cid = cid
                    break

            if current_cid is None:
                # No phase covers this day — treat as 0 contribution (the
                # plant isn't "in" any chamber we know about). This matches
                # legacy behaviour.
                if running is not None:
                    cumulative[cursor] = running
                else:
                    cumulative[cursor] = None
            elif cursor not in self.get_chamber_coverage_days(current_cid):
                # Gap day: chamber had no env observations. Once we've
                # missed any day, cumulative from here on is unreliable.
                self.last_gap_days.add(cursor)
                running = None
                cumulative[cursor] = None
            else:
                daily_map = self.get_chamber_daily_gdd(current_cid)
                contrib = daily_map.get(cursor, 0.0)
                if running is not None:
                    running += contrib
                cumulative[cursor] = running
            cursor += day

        # 2. Find anchor day = first day the plant is in the anchor chamber.
        anchor_chamber_id = self._chamber_id_map().get(anchor_chamber_code)
        anchor_day: Optional[date] = None
        if anchor_chamber_id is not None:
            for seg_start, _seg_end, cid in segments:
                if cid == anchor_chamber_id:
                    anchor_day = seg_start
                    break

        if anchor_day is None:
            # Fallback: plant never entered anchor chamber; leave the
            # cumulative curve starting at 0 on first_entry (this is already
            # how `cumulative` was built above — no shift needed).
            return cumulative

        # 3. Shift so GDD=0 at anchor_day. If the anchor day itself fell
        #    in a gap, we have no valid reference — return all-None.
        anchor_value = cumulative.get(anchor_day)
        if anchor_value is None:
            return {d: None for d in cumulative}
        return {
            d: (None if v is None else v - anchor_value)
            for d, v in cumulative.items()
        }

    # ------------------------------------------------------------------
    # DAS-indexed view (what compare-time-series needs)
    # ------------------------------------------------------------------

    def _plant_sowing_date(self, plant_id: int) -> Optional[date]:
        """Infer sowing date from any raspi observation: sowing = ts - das."""
        if plant_id in self._sowing_cache:
            return self._sowing_cache[plant_id]
        row = (
            self.db.query(
                RaspiObservation.observation_timestamp,
                RaspiObservation.day_after_sewing,
            )
            .filter(RaspiObservation.plant_id == plant_id)
            .filter(RaspiObservation.day_after_sewing.isnot(None))
            .order_by(RaspiObservation.observation_timestamp)
            .first()
        )
        sowing = (
            None
            if row is None
            else row.observation_timestamp.date() - timedelta(days=int(row.day_after_sewing))
        )
        self._sowing_cache[plant_id] = sowing
        return sowing

    def compute_plant_gdd_by_das(
        self,
        plant_id: int,
        anchor_chamber_code: str = DEFAULT_ANCHOR_CHAMBER,
    ) -> Dict[int, Optional[float]]:
        """Return {DAS: gdd_aligned | None} for a plant.

        This is the form endpoints want, because compare-time-series
        aggregates observations into DAS buckets. We reuse the date-indexed
        computation and map dates back to DAS via the plant's sowing date
        (inferred from any raspi observation with (timestamp, das) set).
        None values propagate through — callers should treat them as
        "GDD unavailable for this day" (env gap).
        """
        sowing = self._plant_sowing_date(plant_id)
        if sowing is None:
            return {}
        gdd_by_date = self.compute_plant_gdd_by_date(plant_id, anchor_chamber_code)
        if not gdd_by_date:
            return {}
        result: Dict[int, Optional[float]] = {}
        for d, v in gdd_by_date.items():
            das = (d - sowing).days
            result[das] = v
        return result

    # ------------------------------------------------------------------
    # Pre-G120 GDD — thermal time the plant (via its nursery parent)
    # accumulated in R141/R142 before entering G120. One scalar per
    # individual, to be averaged at the (cultivar, batch) level so that
    # cross-batch GDD-axis comparisons expose hidden differences in
    # pre-anchor thermal history.
    # ------------------------------------------------------------------

    def compute_pre_g120_gdd_for_plant(
        self,
        individual_plant_id: int,
        anchor_chamber_code: str = DEFAULT_ANCHOR_CHAMBER,
    ) -> Optional[float]:
        """Return total bilinear GDD accumulated by the plant's parent
        (nursery_group) from its earliest nursery phase entry up to (but
        not including) this individual's first G120 entry day.

        Returns None when:
          - the plant has no parent_plant_id (unknown nursery history)
          - the individual has no G120 entry (can't bound the pre-G120 window)
          - any day in the parent's nursery phases lacks env coverage
            (same strict-gap policy as post-anchor GDD)
        """
        from ..models.phenotype import Plant  # local import to avoid cycle

        anchor_chamber_id = self._chamber_id_map().get(anchor_chamber_code)
        if anchor_chamber_id is None:
            return None

        # G120 entry — prefer cache (warmup-populated). Falls back to a
        # one-shot per-plant query so single-plant callers still work.
        if individual_plant_id in self._g120_entry_cache:
            g120_entry_date = self._g120_entry_cache[individual_plant_id]
        else:
            g120_entry_row = (
                self.db.query(PlantChamberHistory.entry_date)
                .filter(PlantChamberHistory.plant_id == individual_plant_id)
                .filter(PlantChamberHistory.chamber_id == anchor_chamber_id)
                .order_by(PlantChamberHistory.entry_date)
                .first()
            )
            g120_entry_date = g120_entry_row.entry_date if g120_entry_row else None
            self._g120_entry_cache[individual_plant_id] = g120_entry_date
        if g120_entry_date is None:
            return None

        # parent_id — same cache-or-query pattern.
        if individual_plant_id in self._parent_id_cache:
            parent_id = self._parent_id_cache[individual_plant_id]
        else:
            parent_id = (
                self.db.query(Plant.parent_plant_id)
                .filter(Plant.id == individual_plant_id)
                .scalar()
            )
            self._parent_id_cache[individual_plant_id] = parent_id
        if parent_id is None:
            return None

        parent_phases = self._plant_phases(parent_id)
        if not parent_phases:
            return None

        total = 0.0
        day = timedelta(days=1)
        for chamber_id, _code, entry, exit_ in parent_phases:
            if entry is None:
                continue
            # Clamp each parent phase to [entry, min(exit, g120_entry_date)).
            end = exit_ or g120_entry_date
            if end > g120_entry_date:
                end = g120_entry_date
            if end <= entry:
                continue
            coverage = self.get_chamber_coverage_days(chamber_id)
            daily_map = self.get_chamber_daily_gdd(chamber_id)
            cursor = entry
            while cursor < end:
                if cursor not in coverage:
                    return None
                total += daily_map.get(cursor, 0.0)
                cursor += day
        return total

    def compute_pre_g120_gdd_for_plants(
        self,
        individual_plant_ids: List[int],
        anchor_chamber_code: str = DEFAULT_ANCHOR_CHAMBER,
    ) -> Dict[int, Optional[float]]:
        """Return {individual_plant_id: pre_g120_gdd | None}."""
        # Same warmup as compute_plants_gdd_by_das. Idempotent; if both
        # are called in one request only the first incurs the queries.
        anchor_chamber_id = self._chamber_id_map().get(anchor_chamber_code)
        self._warmup_plants(individual_plant_ids, anchor_chamber_id)

        out: Dict[int, Optional[float]] = {}
        for pid in individual_plant_ids:
            try:
                out[pid] = self.compute_pre_g120_gdd_for_plant(pid, anchor_chamber_code)
            except Exception as e:
                logger.warning(f"pre-G120 GDD failed for plant {pid}: {e}")
                out[pid] = None
        return out

    # ------------------------------------------------------------------
    # Batch helper — compute GDD curves for many plants in one go
    # ------------------------------------------------------------------

    def _plant_segments(self, plant_id: int) -> List[Tuple[date, date, int]]:
        """The plant's chamber residence as [(start, end, chamber_id)]."""
        phases = self._plant_phases(plant_id)
        if not phases:
            return []
        last_exit = max((p[3] or p[2]) for p in phases if (p[3] or p[2]) is not None)
        segs = []
        for chamber_id, _code, entry, exit_ in phases:
            if entry is None:
                continue
            segs.append((entry, exit_ or last_exit, chamber_id))
        return segs

    def compute_plant_gdd_at_timestamps(
        self,
        plant_id: int,
        timestamps: List[datetime],
        anchor_chamber_code: str = DEFAULT_ANCHOR_CHAMBER,
    ) -> Dict[datetime, Optional[float]]:
        """Aligned cumulative GDD **at each timestamp**, not merely per day.

        The model accumulates hourly, so thermal time is defined at any instant:
        value(t) = (cumulative through the end of t's day) − (that day's hours after t).
        Two frames of the same day therefore differ, which is what makes a per-frame
        series against GDD meaningful rather than a stack of points on one x.

        The day-level rules are inherited unchanged from
        `compute_plant_gdd_by_date`: a day whose chamber has no environment record is
        None, and so is every day after it (the integral is biased once an hour is
        missed), and the anchor day is 0.
        """
        by_date = self.compute_plant_gdd_by_date(plant_id, anchor_chamber_code)
        if not by_date:
            return {ts: None for ts in timestamps}
        segments = self._plant_segments(plant_id)

        # Per (chamber, day): the hours of that day and their contributions. Cached
        # across timestamps because a plant has a few dozen days and a few hundred frames.
        day_hours: Dict[Tuple[int, date], Dict[int, float]] = {}

        def hours_of(cid: int, d: date) -> Dict[int, float]:
            key = (cid, d)
            if key not in day_hours:
                day_hours[key] = {
                    h.hour: v for h, v in self.get_chamber_hourly_gdd(cid).items()
                    if h.date() == d
                }
            return day_hours[key]

        out: Dict[datetime, Optional[float]] = {}
        for ts in timestamps:
            d = ts.date()
            end_of_day = by_date.get(d)
            if end_of_day is None:
                out[ts] = None
                continue
            cid = next((c for s, e, c in segments if s <= d <= e), None)
            if cid is None:
                out[ts] = end_of_day
                continue
            hrs = hours_of(cid, d)
            # Everything after the frame is subtracted; the frame's own hour counts
            # pro rata by minutes, so a 09:30 frame gets half of that hour.
            after = sum(v for h, v in hrs.items() if h > ts.hour)
            own = hrs.get(ts.hour, 0.0) * (1.0 - ts.minute / 60.0)
            out[ts] = end_of_day - after - own
        return out

    def compute_plants_gdd_by_das(
        self,
        plant_ids: List[int],
        anchor_chamber_code: str = DEFAULT_ANCHOR_CHAMBER,
    ) -> Tuple[Dict[int, Dict[int, Optional[float]]], Set[date]]:
        """Return ({plant_id: {DAS: gdd | None}}, union_of_gap_days).

        The second return value is the union of env-gap days encountered
        across all plants — callers summarise it into a response-level
        gdd_metadata (affected batches, gap date range, etc.).
        """
        # Warm up per-plant caches in ~4 bulk queries before the per-plant
        # loop, so each compute_plant_gdd_by_das call hits in-memory data
        # instead of issuing 6+ DB roundtrips. Idempotent — safe to call
        # again from compute_pre_g120_gdd_for_plants in the same request.
        anchor_chamber_id = self._chamber_id_map().get(anchor_chamber_code)
        self._warmup_plants(plant_ids, anchor_chamber_id)

        out: Dict[int, Dict[int, Optional[float]]] = {}
        gap_days: Set[date] = set()
        for pid in plant_ids:
            try:
                out[pid] = self.compute_plant_gdd_by_das(pid, anchor_chamber_code)
                gap_days.update(self.last_gap_days)
            except Exception as e:
                logger.warning(f"GDD computation failed for plant {pid}: {e}")
                out[pid] = {}
        return out, gap_days
