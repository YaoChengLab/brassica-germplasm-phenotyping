#!/usr/bin/env python3
"""Growth-curve traits per plant from the platform's daily export.

Computes the ten growth-curve traits of Supplementary Table S4 (IDs 84-93)
from a trait export made with level=day, which gives one row per plant and
imaging day with the day's mean leaf_area and leaf_count:

  emg_rate            slope of leaf count against DAS                 count/d
  count_ref           leaf count interpolated to the batch reference day
  area_rate           slope of projected leaf area against DAS          px^2/d
  rgr_slope           slope of ln(area) against DAS, zero-area days dropped   1/d
  area_plateau_ratio  slope of the last third / slope of the first third
                      (needs >= 6 days)
  area_ref            area interpolated to the batch reference day        px^2
  A, t_inf, agr_max, rgr50
                      Gompertz fit A*exp(-exp(-k(t - t_inf))) to area (needs
                      >= 5 days); agr_max = A*k/e, rgr50 = k*ln 2

The batch reference day is the last day on which every plant of the batch
still has data (min over plants of their last DAS). It therefore depends on
which plants the export contains.

Run it on an export such as

  /api/v1/export/traits.csv?batch_codes=2025B08&level=day&day_mode=all
      &frame_pick=all&traits=leaf_area,leaf_count

  python analysis/growth_params.py export.csv growth.csv

Uses numpy and scipy only, so it runs in the imaging environment.
"""
import csv
import sys

import numpy as np
from scipy.optimize import curve_fit

KEY = ("batch_code", "cultivar_code", "treatment_code", "replicate_code")
TRAITS = ("emg_rate", "count_ref", "area_rate", "rgr_slope", "area_plateau_ratio",
          "area_ref", "A", "t_inf", "agr_max", "rgr50")


def slope(xs, ys):
    return float(np.polyfit(xs, ys, 1)[0]) if len(xs) >= 2 else np.nan


def log_slope(xs, ys):
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    m = ys > 0
    if m.sum() < 2:
        return np.nan
    return float(np.polyfit(xs[m], np.log(ys[m]), 1)[0])


def plateau_ratio(xs, ys):
    """Slope of the last third over slope of the first third; << 1 means a plateau."""
    n = len(xs)
    if n < 6:
        return np.nan
    k = n // 3
    e = slope(xs[:k], ys[:k])
    l = slope(xs[-k:], ys[-k:])
    return float(l / e) if e not in (0,) and np.isfinite(e) and abs(e) > 1e-12 else np.nan


def _gompertz(t, A, k, ti):
    return A * np.exp(-np.exp(-k * (t - ti)))


def fit_gompertz(xs, ys):
    """(A, k, t_inf, agr_max, rgr50, r2, converged)."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    if len(xs) < 5 or ys.max() <= 0:
        return (np.nan,) * 6 + (0,)
    p0 = [ys.max() * 1.1, 0.2, float(np.median(xs))]
    bounds = ([ys.max() * 0.5, 0.01, xs.min() - 10], [ys.max() * 5, 2.0, xs.max() + 20])
    try:
        popt, _ = curve_fit(_gompertz, xs, ys, p0=p0, bounds=bounds, maxfev=20000)
    except Exception:
        return (np.nan,) * 6 + (0,)
    A, k, ti = popt
    resid = ys - _gompertz(xs, *popt)
    ss_res = float(np.sum(resid ** 2)); ss_tot = float(np.sum((ys - ys.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return float(A), float(k), float(ti), float(A * k / np.e), float(k * np.log(2)), float(r2), 1


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def read_series(path):
    """{plant key: [(das, area, count), ...]} sorted by DAS; rows lacking a value are dropped."""
    series = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            das, area, cnt = _num(r["das"]), _num(r["leaf_area"]), _num(r["leaf_count"])
            if np.isnan(das) or np.isnan(area) or np.isnan(cnt):
                continue
            series.setdefault(tuple(r[k] for k in KEY), []).append((das, area, cnt))
    return {k: sorted(v) for k, v in series.items()}


def growth_params(series):
    last_day = {}
    for key, rows in series.items():
        last = rows[-1][0]
        last_day[key[0]] = min(last_day.get(key[0], last), last)

    out = []
    for key, rows in series.items():
        xs = np.array([r[0] for r in rows]); ar = np.array([r[1] for r in rows])
        cnt = np.array([r[2] for r in rows])
        ref = last_day[key[0]]
        A, k, ti, agr_max, rgr50, r2, ok = fit_gompertz(xs, ar)
        out.append(dict(
            zip(KEY, key), n_days=len(xs), das_min=xs[0], das_max=xs[-1], das_ref=ref,
            emg_rate=slope(xs, cnt), count_ref=float(np.interp(ref, xs, cnt)),
            area_rate=slope(xs, ar), rgr_slope=log_slope(xs, ar),
            area_plateau_ratio=plateau_ratio(xs, ar), area_ref=float(np.interp(ref, xs, ar)),
            A=A, t_inf=ti, agr_max=agr_max, rgr50=rgr50, fit_r2=r2, fit_valid=ok,
        ))
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: growth_params.py <daily export CSV> <output CSV>")
    rows = growth_params(read_series(sys.argv[1]))
    cols = list(KEY) + ["n_days", "das_min", "das_max", "das_ref"] + list(TRAITS) + ["fit_r2", "fit_valid"]
    with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} plants -> {sys.argv[2]}; Gompertz converged for "
          f"{sum(r['fit_valid'] for r in rows)}")


if __name__ == "__main__":
    main()
