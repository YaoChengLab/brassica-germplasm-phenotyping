// Plant-first query + viewer (B3/B4/B5 frontend).
// Four-column business key -> unique plant (accession-style) -> growth curves + per-plant images.
// Layout: left rail = 4 cascading selectors, right = wide accession header + curves + images.
// Growth curve uses a continuous fractional-DAS x-axis (one tick per day) so labels never repeat
// and every frame stays a distinct point -> hovering the curve scrubs the matching image.
import React, {
  useState, useMemo, useEffect, useRef,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueries } from '@tanstack/react-query';
import { useComparison } from '../contexts/ComparisonContext';
import {
  Container, Row, Col, Form, Card, Spinner, Alert, Badge, Button, Table,
} from 'react-bootstrap';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush, ReferenceLine,
} from 'recharts';
import {
  fetchBatchesWithCultivars, fetchPlantsFor, fetchPlantsForSelection, resolvePlant,
  fetchPlantObservations, fetchPlantFrames, plantImageUrl, plantOverlayUrl, qcDeepLink,
} from '../services/plantViewService';
import Combobox from '../components/Combobox';
import { fetchExportOptions } from '../services/exportService';

const QC_COLORS = { verified: '#2ca02c', auto: '#1f77b4', no: '#d62728' };
const QC_LABELS = { verified: 'human-reviewed', auto: 'auto-assigned', no: 'pre-QC' };
const qcBadge = (s) => <Badge bg="" style={{ backgroundColor: QC_COLORS[s] || '#888' }}>{s}</Badge>;

// Left/right axis colours, matching the Cultivar page's growth curves.
const TRAIT_COLORS = ['#2ca02c', '#1f77b4'];

// Compare mode: colour identifies the *plant*, assigned in fixed slot order and never
// cycled. Validated as a set (adjacent pairlist, light surface): worst adjacent CVD
// ΔE 9.1, worst normal-vision ΔE 19.6. Three slots sit below 3:1 against the surface,
// so identity never rests on colour alone — every series is named in the legend and in
// the per-plant table below the chart.
const PLANT_COLORS = [
  '#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948',
];
// Past eight, colour stops being able to carry identity; the set is capped and what was
// dropped is stated on screen rather than silently truncated.
// The x axis gets a band tall enough for ticks *and* its title: the title is drawn
// inside the axis band, and the Brush is laid out directly under it, so without the
// extra height the window selector covers 'DAS (days)'.
const DAS_AXIS_HEIGHT = 34;

// The axis title lives in its own element under the chart rather than inside the tick
// band: the Brush is laid out immediately below that band, so a title drawn in it is
// covered by the window selector at any band height. Same reason the y-axis titles were
// moved out — overlap should be structurally impossible, not tuned.
// An empty chart would read as "this plant has no data". It has data; the chambers it
// lived in have no environment records for those days, which is a different statement.
const GddGap = ({ anchor }) => (
  <Alert variant="warning" className="mb-0">
    <strong>No thermal time for these plants.</strong> They have observations, but there is no
    environment record for their chamber on any imaging day, so GDD aligned on {anchor} entry cannot
    be computed. Empty is not 0. Switch the x axis back to DAS.
  </Alert>
);

const AxisTitle = ({ text }) => (
  <div className="text-center text-muted" style={{ fontSize: 15, marginTop: 2 }}>{text}</div>
);

const MAX_COMPARE = PLANT_COLORS.length;

const plantLabel = (p) => `${p.batch_code}·${p.cultivar_code}·${p.treatment_code || '—'}·${p.replicate_code}`;

// Replicate left as "(all)" means the cultivar's replicates together — the default,
// because "how do this cultivar's four plants compare" is the first question asked of a
// cultivar. Picking one replicate narrows to that single plant.
const ALL_REPS = '*';

// Traits span leaf_area (~10^4 px) to circularity (~0.5), so the number of decimals
// follows the magnitude instead of being fixed per trait. Used for single labelled
// values (tooltip, summary table), where each number carries its own name.
const fmtValue = (v) => {
  if (v == null || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  const a = Math.abs(n);
  if (a >= 1000) return Math.round(n).toLocaleString();
  if (a >= 10) return n.toFixed(1);
  if (a >= 0.01 || a === 0) return n.toFixed(3);
  return n.toExponential(2);
};

// Axis ticks need one rule for the whole axis, not per tick: deciding from each tick's
// own magnitude puts "0.000" next to "15,000" on the same scale. Decimals come from the
// data's magnitude, and an all-integer trait (leaf_count) keeps integer ticks.
const axisTickFormatter = (values) => {
  const nums = values.filter((v) => v != null && !Number.isNaN(v));
  const max = nums.length ? Math.max(...nums.map(Math.abs)) : 0;
  const allInt = nums.length > 0 && nums.every((v) => Number.isInteger(v));
  const digits = allInt ? 0 : max >= 1000 ? 0 : max >= 10 ? 1 : max >= 1 ? 2 : 3;
  return (v) => Number(v).toLocaleString(undefined, {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
};

// Focused series marker: filled = human-verified frame, hollow = not (auto or pre-QC).
// Shape rather than colour, because colour is already spoken for by plant identity.
const compareDot = (color) => function CompareDot({ cx, cy, payload }) {
  if (cx == null || cy == null) return null;
  const verified = payload.qc_status === 'verified';
  return (
    <circle cx={cx} cy={cy} r={3.5} fill={verified ? color : '#fff'} stroke={color} strokeWidth={1.5} />
  );
};

// One <select> over all 110 exportable traits, signature set first, then by category.
// The list comes from the export options endpoint — the same single definition the
// export form and the CSV use, so there is no second trait list to drift.
function TraitSelect({ value, onChange, options, allowNone, label }) {
  return (
    <span className="d-flex align-items-center gap-1">
      <span className="small text-muted">{label}</span>
      <Form.Select size="sm" style={{ width: 230 }} value={value} onChange={(e) => onChange(e.target.value)}>
        {allowNone && <option value="">(none)</option>}
        {options?.signature_traits?.length && (
          <optgroup label="Signature">
            {options.signature_traits.map((t) => <option key={t} value={t}>{t}</option>)}
          </optgroup>
        )}
        {Object.entries(options?.trait_categories || {}).map(([cat, cols]) => (
          <optgroup key={cat} label={cat}>
            {cols.map((t) => <option key={t} value={t}>{t}</option>)}
          </optgroup>
        ))}
      </Form.Select>
    </span>
  );
}

// ISO timestamp -> YYYYMMDDHHMM key (matches frame.ts from the crop filename; no tz math).
const tsKey = (iso) => (iso ? iso.replace(/[-:T]/g, '').slice(0, 12) : null);

// One double-buffered image layer: keeps the last loaded src on screen while the next
// loads underneath, then promotes it on load. Prevents white flashes during fast scrubbing.
function BufferedLayer({ url }) {
  const [loaded, setLoaded] = useState(url);
  const [pending, setPending] = useState(null);
  useEffect(() => {
    if (!url || url === loaded) return;
    setPending(url);
  }, [url, loaded]);
  const fill = { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'contain' };
  return (
    <>
      {loaded && <img src={loaded} alt="" style={fill} />}
      {pending && pending !== loaded && (
        <img key={pending} src={pending} alt="" onLoad={() => { setLoaded(pending); setPending(null); }}
          style={{ ...fill, opacity: 0 }} />
      )}
    </>
  );
}

// Base crop + optional transparent segmentation/ownership overlay, both double-buffered
// so scrubbing (and toggling the overlay) never flashes.
//
// `square`: size the box by its own width with a 1:1 ratio instead of a fixed height. The
// crops are square, so a fixed height inside a wide grid cell letterboxes them — the image
// renders at the height and wastes the rest of the cell. Every tile still gets the same box,
// which is what keeps magnification comparable across plants.
function FrameStage({
  plantId, stem, showOverlay, height = 440, square = false, maxSide,
}) {
  const box = square
    ? {
      position: 'relative', width: '100%', maxWidth: maxSide, aspectRatio: '1 / 1', margin: '0 auto',
    }
    : { position: 'relative', width: '100%', height };
  return (
    <div style={box}>
      <BufferedLayer url={stem ? plantImageUrl(plantId, stem) : null} />
      {showOverlay && <BufferedLayer url={stem ? plantOverlayUrl(plantId, stem) : null} />}
    </div>
  );
}

export default function PlantViewPage() {
  const [batch, setBatch] = useState('');
  const [cultivar, setCultivar] = useState('');
  const [treatment, setTreatment] = useState('');
  const [replicate, setReplicate] = useState('');
  const [pinnedStem, setPinnedStem] = useState(null);   // click-to-pin
  const [hoverStem, setHoverStem] = useState(null);      // transient scrub preview
  const [prefetch, setPrefetch] = useState({ done: 0, total: 0 });
  const [showOverlay, setShowOverlay] = useState(false); // opt-in segmentation overlay
  const [ovPrefetch, setOvPrefetch] = useState({ done: 0, total: 0 });
  // Which traits the curve plots. Any of the 110 exportable columns: this page is where
  // a value is checked against the image that produced it, so it has to be able to show
  // the trait you are about to export, not just leaf area and leaf count.
  // One trait by default. A second one is opt-in (`right`, `(none)` puts it away again):
  // it needs its own scale, and two scales invite reading a crossing as an event.
  const [traitLeft, setTraitLeft] = useState('leaf_area');
  const [traitRight, setTraitRight] = useState('');
  // Compare mode: several plants, one trait. Differences between plants are what a
  // second axis cannot show, so the second trait steps aside here.
  const [compareOn, setCompareOn] = useState(false);
  const [dailyMean, setDailyMean] = useState(false);
  // x axis: plant age (DAS) or aligned thermal time. GDD is a per-day quantity walked
  // through the chamber history, so on that axis every frame of a day shares one x —
  // the series is therefore aggregated to one point per day (see chartData/compareSeries).
  const [xMode, setXMode] = useState('das');
  const gddMode = xMode === 'gdd';
  const [focusId, setFocusId] = useState(null); // whose frames the image panel shows
  // Frame grid: every compared plant's image at the same point in time, side by side.
  // Grid on by default: with several plants on screen, comparing one frame is not
  // the job — the tiles are. Two columns keeps each tile large enough to judge.
  const [gridOn, setGridOn] = useState(true);
  const [gridCols, setGridCols] = useState(2);
  const [hoverX, setHoverX] = useState(null);      // curve position under the cursor
  const [pinnedX2, setPinnedX2] = useState(null);   // clicked curve position
  const [dayOverride, setDayOverride] = useState(null); // DAS chosen with the stepper
  const navigate = useNavigate();
  const {
    comparisonItems, addToComparison, removeFromComparison, isInComparison, clearComparison,
    analysisWindow, setAnalysisWindow,
  } = useComparison();
  const [winStart, setWinStart] = useState(0);   // brush-selected DAS window (indices into chartData)
  const [winEnd, setWinEnd] = useState(0);
  // recharts 2.15 kills a brush drag if the Brush's `startIndex` prop disagrees with the
  // chart's own window while the children compare unequal: the chart bumps `updateId`,
  // and Brush.getDerivedStateFromProps then rebuilds its scale with
  // `isTravellerMoving: false` — one step per gesture. `renderBrush` overrides those
  // props with the chart's `dataStartIndex/dataEndIndex` anyway, so they are passed ONLY
  // when the window is being forced from outside (reset, typed bounds, new dataset) and
  // dropped again on the next render, which leaves dragging alone.
  const [brushForce, setBrushForce] = useState(null);


  // Same cache entry as the export form's options (shared queryKey): one trait list.
  const traitOptsQ = useQuery({
    queryKey: ['export-options'], queryFn: fetchExportOptions, staleTime: Infinity,
  });
  const traitOpts = traitOptsQ.data;

  const batchesQ = useQuery({ queryKey: ['pv-batches'], queryFn: fetchBatchesWithCultivars });
  const batches = batchesQ.data || [];
  const cultivars = useMemo(
    () => (batches.find((b) => b.batch_code === batch)?.cultivars) || [],
    [batches, batch],
  );
  const productName = useMemo(
    () => cultivars.find((c) => c.cultivar_code === cultivar)?.product_name || '',
    [cultivars, cultivar],
  );

  const plantsQ = useQuery({
    queryKey: ['pv-plants', batch, cultivar],
    queryFn: () => fetchPlantsFor(batch, cultivar),
    enabled: !!batch && !!cultivar,
  });
  const plants = plantsQ.data || [];

  // Treatment + replicate are now two explicit columns (4 fields determine a unique plant).
  const treatments = useMemo(
    () => [...new Set(plants.map((p) => p.treatment_code))].sort(),
    [plants],
  );
  const replicates = useMemo(
    () => plants.filter((p) => p.treatment_code === treatment)
      .map((p) => p.replicate_code)
      .sort((a, b) => Number(a) - Number(b)),
    [plants, treatment],
  );
  // Auto-select when a batch has only one treatment (still shown as its own field).
  useEffect(() => {
    if (treatments.length === 1 && !treatment) setTreatment(treatments[0]);
  }, [treatments, treatment]);

  // Combobox option lists — labels are what the keyword search matches against.
  const batchOpts = useMemo(
    () => batches.map((b) => ({ value: b.batch_code, label: b.batch_code })),
    [batches],
  );
  const cultivarOpts = useMemo(
    () => cultivars.map((c) => ({
      value: c.cultivar_code,
      label: c.product_name ? `${c.cultivar_code} — ${c.product_name}` : c.cultivar_code,
    })),
    [cultivars],
  );
  const treatmentOpts = useMemo(() => treatments.map((t) => ({ value: t, label: t })), [treatments]);
  const replicateOpts = useMemo(() => [
    { value: ALL_REPS, label: `(all${replicates.length ? ` — ${replicates.length} plants` : ''})` },
    ...replicates.map((r) => ({ value: r, label: `rep-${r}` })),
  ], [replicates]);
  // Default to all replicates as soon as a cultivar/treatment is picked.
  useEffect(() => {
    if (replicates.length && !replicate) setReplicate(ALL_REPS);
  }, [replicates, replicate]);

  // The plants of the current batch x cultivar x treatment: what "(all)" browses.
  const browsePlants = useMemo(
    () => plants.filter((p) => p.treatment_code === treatment)
      .sort((a, b) => Number(a.replicate_code) - Number(b.replicate_code)),
    [plants, treatment],
  );
  const browsingAll = replicate === ALL_REPS && browsePlants.length > 0;

  const plantSel = useMemo(
    () => plants.find((p) => p.treatment_code === treatment
      && String(p.replicate_code) === String(replicate)) || null,
    [plants, treatment, replicate],
  );
  const plantId = plantSel?.plant_id;


  // ---------------------------------------------------------------- compare mode
  // The plants compared are the export selection: what you compare here is what you
  // quantify in the CSV, so the two cannot drift apart. Each selection row is resolved
  // on its own — a row naming only a cultivar means every plant of it, and rows are
  // never merged into one query (that would cross-multiply).
  const selectionQs = useQueries({
    queries: comparisonItems.map((it) => ({
      queryKey: ['pv-sel-plants', it.batch_code || '', it.cultivar_code || '',
        it.treatment_code || '', it.replicate_code ?? ''],
      queryFn: () => fetchPlantsForSelection(it),
      // Always resolved, not only while comparing: the selection table lists plants, and a
      // row that names a cultivar has to be expanded before it can be shown or pruned.
      staleTime: 5 * 60 * 1000,
    })),
  });
  const selectionSig = selectionQs.map((q) => q.dataUpdatedAt).join(',');
  const selectionLoading = selectionQs.some((q) => q.isLoading);
  const selectedPlants = useMemo(() => {
    const seen = new Map();
    // /query/plants returns the surrogate key as `plant_id`, not `id` — reading the
    // wrong name collapsed every plant into a single `undefined` series.
    selectionQs.forEach((q) => (q.data || []).forEach((p) => {
      if (p.plant_id != null && !seen.has(p.plant_id)) seen.set(p.plant_id, p);
    }));
    return [...seen.values()].sort((a, b) => (
      String(a.batch_code).localeCompare(String(b.batch_code))
      || String(a.cultivar_code).localeCompare(String(b.cultivar_code))
      || String(a.treatment_code || '').localeCompare(String(b.treatment_code || ''))
      || Number(a.replicate_code) - Number(b.replicate_code)
    ));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionSig]);
  const comparePlants = useMemo(() => selectedPlants.slice(0, MAX_COMPARE), [selectedPlants]);
  const droppedPlants = selectedPlants.length - comparePlants.length;

  // What is on screen, in strict order of precedence, so it is always answerable in one
  // sentence: comparing the export selection wins; otherwise "(all)" browses the current
  // cultivar's replicates; otherwise it is the one selected plant.
  //   Browsing does NOT touch the export selection — landing on a cultivar must not
  //   quietly fill the cart with plants you only looked at.
  // 🔑 Memoised, not derived inline: `browsePlants.slice()` produced a new array on every
  // render, which invalidated the series/rows memos, which made the chart see a new `data`
  // array, which made recharts call `createDefaultState()` — resetting the brush window to
  // the full range and rebuilding the Brush's scale. That is what made dragging the window
  // impossible (one step per gesture, traveller frozen): not the brush code, an identity leak.
  const multiPlants = useMemo(
    () => (compareOn ? comparePlants : (browsingAll ? browsePlants.slice(0, MAX_COMPARE) : [])),
    [compareOn, comparePlants, browsingAll, browsePlants],
  );
  const multiMode = multiPlants.length > 0;
  const multiSource = compareOn ? 'selection' : 'browse';
  const browseDropped = browsingAll ? Math.max(0, browsePlants.length - multiPlants.length) : 0;

  // One series query per plant, same cache key shape as the single-plant view so
  // switching between the modes re-uses what is already fetched.
  const seriesQs = useQueries({
    queries: multiPlants.map((p) => ({
      queryKey: ['pv-obs', p.plant_id, traitLeft, traitRight, xMode],
      queryFn: () => fetchPlantObservations(p.plant_id, {
        fields: [traitLeft, traitRight].filter(Boolean), includeGdd: gddMode,
      }),
      enabled: !!traitLeft,
    })),
  });
  const seriesSig = seriesQs.map((q) => q.dataUpdatedAt).join(',');
  const seriesLoading = seriesQs.some((q) => q.isLoading);

  const compareSeries = useMemo(() => multiPlants.map((p, i) => {
    const raw = (seriesQs[i]?.data?.data || []).map((o) => {
      const iso = o.observation_timestamp || '';
      const hh = Number(iso.slice(11, 13)) || 0;
      const mm = Number(iso.slice(14, 16)) || 0;
      const das = o.day_after_sewing;
      const gdd = o.gdd_aligned == null ? null : Number(o.gdd_aligned);
      return {
        // GDD accumulates hourly, so it is defined per frame as well — no need to
        // collapse the series to one point per day on that axis.
        x: gddMode ? gdd : (das != null ? das + (hh * 60 + mm) / 1440 : null),
        das,
        gdd,
        datetime: iso ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : '',
        ts: tsKey(iso),
        qc_status: o.qc_status,
        v: o[traitLeft] == null ? null : Number(o[traitLeft]),
        v2: !traitRight || o[traitRight] == null ? null : Number(o[traitRight]),
      };
    }).filter((d) => d.x != null);
    // Daily mean collapses the frames of a day to one point per plant: readable when
    // several plants overlap, at the cost of hiding frame-level outliers — which is
    // exactly what the per-frame mode is for.
    let points = raw;
    if (dailyMean) {
      const byDas = new Map();
      raw.forEach((r) => {
        if (r.v == null) return;
        const acc = byDas.get(r.das) || { sum: 0, n: 0, sum2: 0, n2: 0, gsum: 0, gn: 0, first: r };
        acc.sum += r.v; acc.n += 1;
        if (r.v2 != null) { acc.sum2 += r.v2; acc.n2 += 1; }
        if (r.gdd != null) { acc.gsum += r.gdd; acc.gn += 1; }
        byDas.set(r.das, acc);
      });
      points = [...byDas.entries()].sort((a, b) => a[0] - b[0]).map(([das, acc]) => ({
        // The daily point sits at the mean thermal time of the frames it averages;
        // a day whose chamber has no record has no x and is dropped, never drawn at 0.
        x: gddMode ? (acc.gn ? acc.gsum / acc.gn : null) : das,
        das, datetime: acc.first.datetime, ts: acc.first.ts,
        qc_status: acc.first.qc_status, v: acc.sum / acc.n, n_frames: acc.n,
        v2: acc.n2 ? acc.sum2 / acc.n2 : null,
      })).filter((p) => p.x != null);
    }
    return {
      plant: p, color: PLANT_COLORS[i], points, raw,
      key: `p${p.plant_id}`,       // left trait: solid line, left axis
      keyR: `p${p.plant_id}R`,     // right trait: dashed line, right axis
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [seriesSig, multiPlants, traitLeft, traitRight, dailyMean, gddMode]);

  // Merged on x. In per-frame mode frames of different plants fall on different
  // timestamps, so rows are sparse and the lines connect across the gaps; in daily-mean
  // mode x is an integer DAS shared by every plant, so a row holds all of them and the
  // tooltip can compare them directly.
  const compareRows = useMemo(() => {
    const byX = new Map();
    compareSeries.forEach((s) => s.points.forEach((pt) => {
      const row = byX.get(pt.x) || { x: pt.x, das: pt.das };
      row[s.key] = pt.v;
      if (pt.v2 != null) row[s.keyR] = pt.v2;
      if (s.plant.plant_id === focusId) {
        row.ts = pt.ts; row.datetime = pt.datetime; row.qc_status = pt.qc_status;
      }
      byX.set(pt.x, row);
    }));
    return [...byX.values()].sort((a, b) => a.x - b.x);
  }, [compareSeries, focusId]);

  // Identity, images and the single-plant series all key off the *focused* plant: with
  // several plants on screen the accession in the left rail, the frames panel and the
  // curve's thick line must name the same one.
  const identityPlant = plantSel
    || multiPlants.find((p) => p.plant_id === focusId)
    || multiPlants[0]
    || null;
  const imagePlantId = identityPlant?.plant_id;
  const resolveQ = useQuery({
    queryKey: ['pv-resolve', imagePlantId],
    queryFn: () => resolvePlant({
      batchCode: identityPlant.batch_code,
      cultivarCode: identityPlant.cultivar_code,
      treatmentCode: identityPlant.treatment_code,
      replicateCode: identityPlant.replicate_code,
    }),
    enabled: !!identityPlant,
  });
  const obsQ = useQuery({
    queryKey: ['pv-obs', imagePlantId, traitLeft, traitRight, xMode],
    queryFn: () => fetchPlantObservations(imagePlantId, {
      fields: [traitLeft, traitRight], includeGdd: gddMode,
    }),
    enabled: !!imagePlantId && !!traitLeft && !multiMode,
  });
  const framesQ = useQuery({
    queryKey: ['pv-frames', imagePlantId],
    queryFn: () => fetchPlantFrames(imagePlantId),
    enabled: !!imagePlantId,
  });

  const meta = resolveQ.data;
  const obs = obsQ.data?.data || [];
  const frames = framesQ.data?.frames || [];
  const hasOverlays = !!framesQ.data?.has_overlays;
  const lastStem = frames.length ? frames[frames.length - 1].stem : null;
  const shownStem = hoverStem || pinnedStem || lastStem;
  const shownTs = useMemo(
    () => frames.find((f) => f.stem === shownStem)?.ts,
    [frames, shownStem],
  );
  const pinnedTs = useMemo(
    () => frames.find((f) => f.stem === pinnedStem)?.ts,
    [frames, pinnedStem],
  );
  const deepLink = meta ? qcDeepLink(meta.business_key) : null;

  // Frames of every compared plant, for the side-by-side grid. One request per plant,
  // same cache key as the single-plant panel.
  const gridFramesQs = useQueries({
    queries: multiPlants.map((p) => ({
      queryKey: ['pv-frames', p.plant_id],
      queryFn: () => fetchPlantFrames(p.plant_id),
      enabled: gridOn && multiMode,
      staleTime: 5 * 60 * 1000,
    })),
  });
  const gridFramesSig = gridFramesQs.map((q) => q.dataUpdatedAt).join(',');

  const inCompare = compareSeries.length > 0;
  // Which plant the image panel and the QC-coloured markers follow. Defaults to the
  // plant selected on the left rail when it is part of the set.
  useEffect(() => {
    if (!multiMode) return;
    if (multiPlants.some((p) => p.plant_id === focusId)) return;
    const preferred = multiPlants.find((p) => p.plant_id === plantId) || multiPlants[0];
    setFocusId(preferred ? preferred.plant_id : null);
  }, [multiMode, multiPlants, focusId, plantId]);
  const focusPlant = multiPlants.find((p) => p.plant_id === focusId) || null;

  // One chart point per frame; x = fractional DAS (day + time-of-day) so nothing overlaps.
  const chartData = useMemo(
    () => {
      const pts = obs.map((o) => {
      const iso = o.observation_timestamp || '';
      const hh = Number(iso.slice(11, 13)) || 0;
      const mm = Number(iso.slice(14, 16)) || 0;
      const das = o.day_after_sewing;
        const gdd = o.gdd_aligned == null ? null : Number(o.gdd_aligned);
        const point = {
          x: gddMode ? gdd : (das != null ? das + (hh * 60 + mm) / 1440 : null),
          das,
          datetime: iso ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : '',
          ts: tsKey(iso),
          qc_status: o.qc_status,
          gdd,
        };
        // Numeric columns arrive as strings/Decimals; recharts needs numbers or it
        // silently draws nothing.
        [traitLeft, traitRight].filter(Boolean).forEach((t) => {
          point[t] = o[t] == null ? null : Number(o[t]);
        });
        return point;
      // Frames whose day has no environment record have no thermal time at all and
      // drop out of the GDD view; they are not plotted at 0.
      }).filter((d) => d.x != null);
      return pts;
    },
    [obs, traitLeft, traitRight, gddMode],
  );
  // The chart, brush and window all run off whichever dataset is on screen: the single
  // plant's frames, or the merged multi-plant rows.
  const activeRows = inCompare ? compareRows : chartData;

  // Where in time the grid is looking: the curve's cursor, else the pinned point, else
  // the day chosen with the stepper, else the last day of the series. Fractional DAS, so
  // scrubbing inside a day also moves the grid to the nearest time of day.
  const lastX = activeRows.length ? activeRows[activeRows.length - 1].x : null;
  const gridTargetX = dayOverride != null ? dayOverride + 0.5 : (hoverX ?? pinnedX2 ?? lastX);

  // Plants were imaged on their own calendar days, so the comparable axis is DAS, not the
  // clock. Each plant contributes the frame nearest the target — and every tile states the
  // frame it actually got, because "nearest" is not "identical": a plant with a gap can
  // land on another day, and that must be visible rather than implied away.
  const gridTiles = useMemo(() => multiPlants.map((p, i) => {
    const data = gridFramesQs[i]?.data;
    const frames = (data?.frames || []).map((f) => {
      const ts = f.ts || '';
      const hh = Number(ts.slice(8, 10)) || 0;
      const mm = Number(ts.slice(10, 12)) || 0;
      return { ...f, x: f.day_after_sewing != null ? f.day_after_sewing + (hh * 60 + mm) / 1440 : null };
    }).filter((f) => f.x != null);
    let best = null;
    if (gridTargetX != null && frames.length) {
      best = frames.reduce((a, b) => (
        Math.abs(b.x - gridTargetX) < Math.abs(a.x - gridTargetX) ? b : a
      ), frames[0]);
    }
    return {
      plant: p,
      color: PLANT_COLORS[i],
      frame: best,
      hasOverlays: !!data?.has_overlays,
      error: gridFramesQs[i]?.isError ? (gridFramesQs[i].error?.response?.status === 503
        ? 'Single-plant images not mounted' : 'Single-plant images unavailable') : null,
      loading: !!gridFramesQs[i]?.isLoading,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [gridFramesSig, multiPlants, gridTargetX]);

  const inGrid = inCompare && gridOn && gridTiles.length > 0;

  const gddAnchor = (obsQ.data?.gdd?.anchor_chamber)
    || (seriesQs.find((q) => q.data?.gdd)?.data?.gdd?.anchor_chamber) || 'G120';
  const xTitle = gddMode ? `GDD (degree-days, 0 = entry into ${gddAnchor})` : 'DAS (days)';
  // Observations exist but none of their days has an environment record: that is a gap in
  // the data, not "no plant" — saying so beats an empty chart, and empty is not zero.
  // In compare mode `raw` already drops points without an x, so test the fetched rows.
  const gddGap = gddMode && activeRows.length === 0
    && (inCompare ? seriesQs.some((q) => (q.data?.data || []).length > 0) : obs.length > 0);

  // One rule for the whole axis, as with the y axes: on DAS every day is a tick; on GDD
  // recharts' own choice came out uneven (0, 95, 190, 368), so the step is picked here.
  const dayTicks = useMemo(() => {
    if (!activeRows.length) return undefined;
    const xs = activeRows.map((r) => r.x);
    const lo = Math.min(...xs);
    const hi = Math.max(...xs);
    if (!gddMode) {
      const t = [];
      for (let d = Math.floor(lo); d <= Math.ceil(hi); d += 1) t.push(d);
      return t;
    }
    const raw = (hi - lo) / 6 || 1;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((v) => v >= raw) || mag * 10;
    const t = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) t.push(Math.round(v * 100) / 100);
    return t;
  }, [activeRows, gddMode]);
  const tsToStem = useMemo(() => {
    const m = new Map();
    frames.forEach((f) => { if (f.ts) m.set(f.ts, f.stem); });
    return m;
  }, [frames]);
  // x of the pinned point → persistent vertical reference line on the curve.
  const pinnedX = useMemo(
    () => (pinnedTs ? (activeRows.find((d) => d.ts === pinnedTs)?.x ?? null) : null),
    [activeRows, pinnedTs],
  );
  // One tick rule per axis, derived from that trait's own values. In compare mode every
  // plant shares the one axis, so the rule comes from all of their values together.
  const tickFmtLeft = useMemo(
    () => axisTickFormatter(inCompare
      ? compareSeries.flatMap((s) => s.points.map((pt) => pt.v))
      : chartData.map((d) => d[traitLeft])),
    [inCompare, compareSeries, chartData, traitLeft],
  );
  const tickFmtRight = useMemo(
    () => axisTickFormatter(inCompare
      ? compareSeries.flatMap((s) => s.points.map((p) => p.v2))
      : chartData.map((d) => d[traitRight])),
    [inCompare, compareSeries, chartData, traitRight],
  );
  // QC mix of the plant the identity card is about. In multi-plant modes the single-plant
  // series is not fetched at all, so the counts come from that plant's compare series —
  // otherwise the card showed an empty QC row.
  const qcCounts = useMemo(() => {
    const c = {};
    const src = multiMode
      ? (compareSeries.find((x) => x.plant.plant_id === imagePlantId)?.raw || [])
      : obs;
    src.forEach((o) => { c[o.qc_status] = (c[o.qc_status] || 0) + 1; });
    return c;
  }, [obs, multiMode, compareSeries, imagePlantId]);

  // Reset the DAS window to the full range whenever the dataset changes (other plant,
  // other trait, compare mode on/off, daily-mean on/off).
  useEffect(() => {
    const last = Math.max(0, activeRows.length - 1);
    setWinStart(0); setWinEnd(last);
    setBrushForce({ start: 0, end: last });
  }, [activeRows.length, plantId, inCompare, dailyMean]);

  // One render with the props, then back to hands-off.
  useEffect(() => { if (brushForce) setBrushForce(null); }, [brushForce]);

  const winLen = activeRows.length;
  const isFullWindow = winStart <= 0 && winEnd >= winLen - 1;
  // The window-reset effect runs *after* the render that first sees a new dataset, so the
  // brush must clamp its own indices — an endIndex past the end makes recharts emit
  // NaN rect/line geometry for one frame.
  const brushEnd = Math.max(0, Math.min(winEnd, winLen - 1));
  const brushStart = Math.max(0, Math.min(winStart, brushEnd));
  // Read-only window summary: derived in-browser from already-fetched observations (no DB, no fetch).
  const winSummary = useMemo(() => {
    const pts = activeRows.slice(winStart, winEnd + 1);
    if (!pts.length) return null;
    const stat = (arr) => (arr.length ? {
      mean: arr.reduce((a, b) => a + b, 0) / arr.length,
      min: Math.min(...arr), max: Math.max(...arr),
      first: arr[0], last: arr[arr.length - 1],
    } : null);
    const dasFrom = pts[0].das;
    const dasTo = pts[pts.length - 1].das;
    // Compare mode: one row per plant for the one trait — this table is how differences
    // between plants get read off, and it is also the non-colour channel for identity.
    // Single mode: one row per plotted trait.
    const rows = inCompare
      ? [
        [traitLeft, 'v', false],
        ...(traitRight ? [[traitRight, 'v2', true]] : []),
      ].flatMap(([trait, field, dashed]) => compareSeries.map((s) => {
        const inWin = s.points.filter((pt) => pt.das >= dasFrom && pt.das <= dasTo);
        const rawInWin = s.raw.filter((pt) => pt.das >= dasFrom && pt.das <= dasTo);
        const qc = {};
        rawInWin.forEach((pt) => { qc[pt.qc_status] = (qc[pt.qc_status] || 0) + 1; });
        const vals = inWin.map((pt) => pt[field]).filter((v) => v != null && !Number.isNaN(v));
        return {
          key: traitRight ? `${plantLabel(s.plant)} · ${trait}` : plantLabel(s.plant),
          color: s.color,
          dashed,
          plantId: s.plant.plant_id,
          n: vals.length,
          qc,
          stat: stat(vals),
        };
      }))
      : [traitLeft, traitRight].filter(Boolean).map((t, i) => ({
        key: t,
        color: TRAIT_COLORS[i],
        stat: stat(pts.map((p) => p[t]).filter((v) => v != null && !Number.isNaN(v))),
      }));
    return {
      n: pts.length,
      dasFrom,
      dasTo,
      dateFrom: pts[0].datetime,
      dateTo: pts[pts.length - 1].datetime,
      traits: rows,
    };
  }, [activeRows, winStart, winEnd, traitLeft, traitRight, inCompare, compareSeries]);

  // Values under the cursor, shown in a fixed strip below the plot instead of a floating
  // card: a tooltip that follows the mouse covers exactly the part of the curve being
  // read, and the numbers jump around while the eye is trying to compare them. The
  // crosshair stays — that is what a tooltip is actually useful for here.
  const readoutX = hoverX ?? pinnedX2 ?? null;
  const readout = useMemo(() => {
    if (readoutX == null || !activeRows.length) return null;
    const row = activeRows.reduce((a, b) => (
      Math.abs(b.x - readoutX) < Math.abs(a.x - readoutX) ? b : a
    ), activeRows[0]);
    const items = inCompare
      ? [
        ...compareSeries.map((ser) => ({ label: plantLabel(ser.plant), color: ser.color, v: row[ser.key] }))
          .filter((it) => it.v != null && !Number.isNaN(it.v))
          .sort((a, b) => b.v - a.v),
        // The second trait is a second scale, so it is read as its own block rather than
        // interleaved by value with the first.
        ...(traitRight ? compareSeries
          .map((ser) => ({
            label: `${plantLabel(ser.plant)} · ${traitRight}`, color: ser.color, dashed: true, v: row[ser.keyR],
          }))
          .filter((it) => it.v != null && !Number.isNaN(it.v))
          .sort((a, b) => b.v - a.v) : []),
      ]
      : [traitLeft, traitRight].filter(Boolean).map((tr, i) => ({
        label: tr, color: TRAIT_COLORS[i], v: row[tr],
      })).filter((it) => it.v != null && !Number.isNaN(it.v));
    return {
      das: row.das,
      datetime: row.datetime,
      qc: row.qc_status,
      pinned: hoverX == null && pinnedX2 != null,
      items,
    };
  }, [readoutX, activeRows, inCompare, compareSeries, traitLeft, traitRight, hoverX, pinnedX2]);

  // Map a DAS value to the nearest row index (for the numeric window inputs).
  const dasToIndex = (das, side) => {
    if (!activeRows.length) return 0;
    if (side === 'from') {
      const i = activeRows.findIndex((d) => d.das >= das);
      return i < 0 ? activeRows.length - 1 : i;
    }
    let i = chartData.length - 1;
    while (i > 0 && chartData[i].das > das) i -= 1;
    return i;
  };

  // Background-prefetch every full-res crop (concurrency-limited) so scrubbing hits browser cache.
  useEffect(() => {
    setHoverStem(null); setPinnedStem(null);
    if (!frames.length || !imagePlantId) { setPrefetch({ done: 0, total: 0 }); return undefined; }
    let cancelled = false;
    let idx = 0;
    let done = 0;
    const CONC = 6;
    setPrefetch({ done: 0, total: frames.length });
    const next = () => {
      if (cancelled || idx >= frames.length) return;
      const f = frames[idx];
      idx += 1;
      const img = new Image();
      img.onload = () => { if (!cancelled) { done += 1; setPrefetch({ done, total: frames.length }); next(); } };
      img.onerror = img.onload;
      img.src = plantImageUrl(imagePlantId, f.stem);
    };
    for (let k = 0; k < CONC; k += 1) next();
    return () => { cancelled = true; };
  }, [frames, imagePlantId]);

  // Prefetch overlays only once the opt-in toggle is on (default off = zero extra load).
  useEffect(() => {
    if (!showOverlay || !hasOverlays || !frames.length || !imagePlantId) {
      setOvPrefetch({ done: 0, total: 0 }); return undefined;
    }
    let cancelled = false;
    let idx = 0;
    let done = 0;
    const CONC = 6;
    setOvPrefetch({ done: 0, total: frames.length });
    const next = () => {
      if (cancelled || idx >= frames.length) return;
      const f = frames[idx];
      idx += 1;
      const img = new Image();
      img.onload = () => { if (!cancelled) { done += 1; setOvPrefetch({ done, total: frames.length }); next(); } };
      img.onerror = img.onload;
      img.src = plantOverlayUrl(imagePlantId, f.stem);
    };
    for (let k = 0; k < CONC; k += 1) next();
    return () => { cancelled = true; };
  }, [showOverlay, hasOverlays, frames, imagePlantId]);

  // rAF-throttled scrub: collapse rapid mouse-move events into ~1 image swap per frame.
  const rafRef = useRef(0);
  const pendingTs = useRef(null);
  const pendingX = useRef(null);
  const activeTs = (state) => state?.activePayload?.[0]?.payload?.ts || null; // robust under brush zoom
  const activeX = (state) => state?.activePayload?.[0]?.payload?.x ?? null;
  const onChartMove = (state) => {
    const ts = activeTs(state);
    const x = activeX(state);
    // The grid follows the curve, so hovering it takes back control from the day stepper.
    if (x != null) { pendingX.current = x; setDayOverride(null); }
    if (!ts && x == null) return;
    if (ts) pendingTs.current = ts;
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      if (pendingTs.current) setHoverStem(tsToStem.get(pendingTs.current) || null);
      if (pendingX.current != null) setHoverX(pendingX.current);
    });
  };
  const onChartLeave = () => { setHoverStem(null); setHoverX(null); };
  const onChartClick = (state) => {
    const ts = activeTs(state);
    if (ts) setPinnedStem(tsToStem.get(ts) || null);
    const x = activeX(state);
    if (x != null) { setPinnedX2(x); setDayOverride(null); }
  };
  useEffect(() => () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); }, []);

  const onPickBatch = (v) => { setBatch(v); setCultivar(''); setTreatment(''); setReplicate(''); };
  const onPickCultivar = (v) => { setCultivar(v); setTreatment(''); setReplicate(''); };
  const onPickTreatment = (v) => { setTreatment(v); setReplicate(''); };
  // How to name a set of accessions: if every plant shares batch/cultivar/treatment, write
  // the prefix once and brace the replicates; otherwise the keys have nothing in common and
  // are listed in full.
  const groupKey = useMemo(() => {
    if (!multiPlants.length) return { text: '', collapsed: false };
    const keyOf = (p) => `${p.batch_code}_${p.cultivar_code}_${p.treatment_code}_${p.replicate_code}`;
    const same = (f) => new Set(multiPlants.map((p) => p[f])).size === 1;
    if (same('batch_code') && same('cultivar_code') && same('treatment_code')) {
      const p0 = multiPlants[0];
      const reps = multiPlants.map((p) => p.replicate_code).join(',');
      return { text: `${p0.batch_code}_${p0.cultivar_code}_${p0.treatment_code}_{${reps}}`, collapsed: true };
    }
    return { text: multiPlants.map(keyOf).join('  '), collapsed: false };
  }, [multiPlants]);
  // The selection keeps the whole business key, not just the cultivar: this page
  // is looking at one plant, and the export form can address exactly that plant.
  // (Search results still add cultivar-only items, which mean every replicate.)
  const selItem = meta && {
    batch_code: meta.batch_code || batch,
    cultivar_code: meta.cultivar_code,
    treatment_code: meta.treatment_code || treatment,
    replicate_code: meta.replicate_code ?? replicate,
    product_name: productName,
    business_key: meta.business_key,
  };
  const inSet = selItem ? isInComparison(selItem) : false;
  const toggleSet = () => {
    if (!selItem) return;
    if (inSet) removeFromComparison(selItem);
    else addToComparison(selItem);
  };
  // Dragging: remember where it is, re-render nothing. Releasing (or a click, which
  // recharts also reports through onChange without a drag) commits it.
  const onBrushChange = (r) => { if (r) { setWinStart(r.startIndex); setWinEnd(r.endIndex); } };
  const resetWindow = () => {
    const last = Math.max(0, winLen - 1);
    setWinStart(0); setWinEnd(last);
    setBrushForce({ start: 0, end: last });
  };
  const setWindowBound = (side) => (value) => {
    const i = dasToIndex(Number(value), side);
    const next = side === 'from' ? { start: i, end: brushEnd } : { start: brushStart, end: i };
    if (side === 'from') setWinStart(i); else setWinEnd(i);
    setBrushForce(next);
  };
  const useAsAnalysisWindow = () => {
    if (winSummary && !isFullWindow) setAnalysisWindow({ das_min: winSummary.dasFrom, das_max: winSummary.dasTo });
  };
  const clearAnalysisWindow = () => setAnalysisWindow(null);
  // The selection and the DAS window are inputs to the export form; the export
  // page reads both from the shared selection, so nothing is passed in the URL
  // (and nothing is copied — the window is bounds, never trait values).
  const goToExport = () => navigate('/export');

  // Removing one plant from the selection. A selection row that names only a cultivar
  // stands for every plant of it, so there is no row to delete for a single plant —
  // that row is flattened into explicit per-plant rows minus the one being removed, which
  // keeps "what is selected", "what is compared" and "what the CSV holds" the same thing.
  // The flattening is reported rather than done quietly: it narrows the export.
  const [selectionNote, setSelectionNote] = useState(null);
  const explicitItem = (p) => ({
    batch_code: p.batch_code,
    cultivar_code: p.cultivar_code,
    treatment_code: p.treatment_code || '',
    replicate_code: String(p.replicate_code),
    product_name: p.product_name,
    business_key: `${p.batch_code}_${p.cultivar_code}_${p.treatment_code || ''}_${p.replicate_code}`,
  });
  const isExplicit = (it) => !!(it.batch_code && it.cultivar_code && it.treatment_code
    && it.replicate_code != null && it.replicate_code !== '');
  const removePlant = (plant) => {
    comparisonItems.forEach((it, i) => {
      const expanded = selectionQs[i]?.data || [];
      if (!expanded.some((p) => p.plant_id === plant.plant_id)) return;
      removeFromComparison(it);
      if (isExplicit(it)) return;
      // Only the plants actually on screen can be re-added (the compare set is capped),
      // so say what the row shrank from and to.
      const keep = comparePlants.filter((p) => p.plant_id !== plant.plant_id
        && expanded.some((e) => e.plant_id === p.plant_id));
      keep.forEach((p) => addToComparison(explicitItem(p)));
      if (expanded.length > keep.length + 1) {
        setSelectionNote(`“${it.cultivar_code}” covered ${expanded.length} plants; it is now the `
          + `${keep.length} plant(s) listed here. The other ${expanded.length - keep.length - 1} are no `
          + 'longer in the export selection — re-add them from Search if you need them.');
      } else {
        setSelectionNote(null);
      }
    });
  };

  const dot = (props) => {
    const { cx, cy, payload } = props;
    if (cx == null || cy == null) return null;
    const pinned = pinnedTs && payload.ts === pinnedTs;
    const hovered = hoverStem && payload.ts === shownTs;
    const r = pinned ? 6 : hovered ? 5 : 3;
    return <circle cx={cx} cy={cy} r={r} fill={QC_COLORS[payload.qc_status] || '#888'}
      stroke={pinned ? '#000' : hovered ? '#555' : 'none'} strokeWidth={pinned ? 2 : hovered ? 1 : 0} />;
  };

  return (
    <Container fluid className="py-4 px-4" style={{ fontSize: '1.08rem' }}>
      <h3 className="mb-3">Plant Viewer</h3>


      <Row>
        {/* Left rail: four cascading selectors */}
        <Col md={3} lg={3} xl={2}>
          {/* zIndex on the card, not on the dropdown: `position: sticky` makes this card
              a stacking context, so the Combobox list's z-index cannot lift it above the
              cards that follow in the DOM — the last replicates were painted over. */}
          <Card className="mb-4" style={{ position: 'sticky', top: '1rem', zIndex: 1020 }}>
            <Card.Header className="small text-muted">Select a plant (4 fields → unique)</Card.Header>
            <Card.Body className="d-grid gap-3">
              <div>
                <Form.Label className="mb-1">Batch</Form.Label>
                <Combobox options={batchOpts} value={batch} onChange={onPickBatch}
                  disabled={batchesQ.isLoading}
                  placeholder={batchesQ.isLoading ? 'Loading…' : 'Type or select batch'} />
              </div>
              <div>
                <Form.Label className="mb-1">Cultivar</Form.Label>
                <Combobox options={cultivarOpts} value={cultivar} onChange={onPickCultivar}
                  disabled={!batch}
                  placeholder="Type code / name (e.g. s0123)" />
              </div>
              <div>
                <Form.Label className="mb-1">Treatment</Form.Label>
                <Combobox options={treatmentOpts} value={treatment} onChange={onPickTreatment}
                  disabled={!cultivar || plantsQ.isLoading}
                  placeholder={plantsQ.isLoading ? 'Loading…' : 'Type or select treatment'} />
              </div>
              <div>
                <Form.Label className="mb-1">Replicate</Form.Label>
                <Combobox options={replicateOpts} value={replicate} onChange={setReplicate}
                  disabled={!treatment}
                  placeholder="Type or select replicate" />
                <div className="text-muted" style={{ fontSize: '0.8rem' }}>
                  {browsingAll
                    ? 'All replicates together; pick one to follow a single plant.'
                    : 'One plant. Choose (all) to see its replicates together.'}
                </div>
              </div>
            </Card.Body>
          </Card>

          {/* Identity of the plant on screen, directly under the selectors that chose it.
              It used to be a wide card across the top, which pushed the curve and the
              frames — the things being read — down the page. With several plants on screen
              this names the focused one, so accession, images and the thick line agree. */}
          {meta && (
            <Card className="mb-4">
              <Card.Header className="small text-muted d-flex justify-content-between align-items-center">
                <span>{multiMode ? `${multiPlants.length} plants on screen` : 'Accession (business key)'}</span>
                {multiMode && (
                  <Badge bg="secondary" className="fw-normal">
                    {multiSource === 'browse' ? 'browsing' : 'selection'}
                  </Badge>
                )}
              </Card.Header>
              <Card.Body className="py-2">
                {/* Two levels, because a set has an identity of its own: the group is named
                    once (shared prefix, varying suffix in braces — the compact way to write
                    a set of accessions), and the record-level detail belongs to whichever
                    plant is focused. Showing one member's key as if it were the set's was
                    the thing that read wrong. */}
                {multiMode && (
                  <div className="mb-2">
                    <div className="text-muted mb-1" style={{ fontSize: '0.78rem' }}>
                      {multiSource === 'browse'
                        ? `All ${multiPlants.length} replicates of ${cultivar}`
                        : `Selected plants (${multiPlants.length})`}
                    </div>
                    <code style={{ fontSize: '0.92rem', wordBreak: 'break-all' }}>{groupKey.text}</code>
                    <div className="d-flex flex-wrap gap-1 mt-1">
                      {multiPlants.map((p, i) => (
                        <Button key={p.plant_id} size="sm" className="py-0 px-2"
                          variant={p.plant_id === imagePlantId ? 'dark' : 'outline-secondary'}
                          onClick={() => setFocusId(p.plant_id)}
                          style={{ borderLeft: `5px solid ${PLANT_COLORS[i]}`, fontSize: '0.8rem' }}
                          title={`${p.batch_code}_${p.cultivar_code}_${p.treatment_code}_${p.replicate_code}`}>
                          {groupKey.collapsed ? `rep-${p.replicate_code}` : plantLabel(p)}
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
                <div className="text-muted" style={{ fontSize: '0.78rem' }}>
                  {multiMode ? 'Focused plant' : 'Business key'}
                </div>
                <div className="d-flex align-items-center gap-2 flex-wrap">
                  <code style={{ fontSize: '1.05rem', wordBreak: 'break-all' }}>{meta.business_key}</code>
                </div>
                <div className="text-muted" style={{ fontSize: '0.8rem' }}>
                  plant_id {meta.plant_id} · {productName}
                </div>
                <Table size="sm" borderless className="mb-2 mt-2" style={{ fontSize: '0.85rem' }}>
                  <tbody>
                    <tr><td className="text-muted">Sowing</td><td>{meta.sewing_date || '—'}</td></tr>
                    <tr><td className="text-muted">DAS</td><td>{meta.das_min}–{meta.das_max} d</td></tr>
                    <tr><td className="text-muted">Single-plant images</td><td>{meta.n_raspi_observations}</td></tr>
                    {/* States only: the count after each badge just repeated the Frames row
                        above whenever a plant is in one state, which it usually is. */}
                    <tr><td className="text-muted">QC</td><td>
                      {Object.entries(qcCounts).map(([k, v]) => (
                        <span key={k} className="me-1">
                          {qcBadge(k)}{Object.keys(qcCounts).length > 1 ? ` ${v}` : ''}
                        </span>
                      ))}
                    </td></tr>
                  </tbody>
                </Table>
                {/* What is on screen is controlled where the thing on screen is named,
                    rather than in a banner across the top: the banner repeated the card's
                    own header and pushed the curve down. */}
                {multiMode && (
                  <>
                    <hr className="my-2" />
                    <Form.Check type="switch" id="daily-mean-switch" className="small"
                      label="Daily mean per plant" checked={dailyMean}
                      onChange={(e) => setDailyMean(e.target.checked)}
                      title="Average the single-plant images of each day; outliers among them become invisible" />
                    <div className="text-muted" style={{ fontSize: '0.78rem' }}>
                      colour = plant · pick a rep above (or a legend entry) to focus its images
                    </div>
                    {browseDropped > 0 && (
                      <div className="small text-danger mt-1">
                        {browsePlants.length} replicates exist; the first {MAX_COMPARE} are shown.
                      </div>
                    )}
                    {multiSource === 'browse' && (
                      <>
                        <Button size="sm" variant="outline-primary" className="w-100 mt-2"
                          onClick={() => multiPlants.forEach((p) => addToComparison(explicitItem(p)))}>
                          + Add these {multiPlants.length} to export selection
                        </Button>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                          Browsing only — the export selection is untouched until you add them.
                        </div>
                      </>
                    )}
                    <hr className="my-2" />
                  </>
                )}
                <Button size="sm" variant={inSet ? 'success' : 'outline-primary'} className="w-100"
                  onClick={toggleSet}>
                  {inSet
                    ? '✓ In export selection'
                    : multiMode ? '+ Add this plant to export selection' : '+ Add to export selection'}
                </Button>
                {deepLink && (
                  <Button size="sm" variant="outline-secondary" className="w-100 mt-1"
                    href={deepLink} target="_blank" rel="noopener noreferrer">
                    Single-plant images + overlay viewer ↗
                  </Button>
                )}
              </Card.Body>
            </Card>
          )}
        </Col>

        {/* Right main: header + curves + images */}
        <Col md={9} lg={9} xl={10}>
          {/* Comparing works without a left-rail selection: arriving from Search with a
              selection already in hand is the normal way into compare mode. */}
          {!plantSel && !multiMode && (
            <Alert variant="secondary">
              Pick a batch and cultivar to see its replicates together, choose one replicate to
              follow a single plant, or switch on “Compare on chart” to plot the plants already
              in the export selection.
            </Alert>
          )}

          {(plantSel || multiMode) && (
            <>
              {/* Growth curve + current frame, side by side at the same height */}
              <Row className="g-3 mb-4">
                <Col lg={6} xl={7}>
                  <Card className="h-100">
                    <Card.Header className="d-flex flex-wrap align-items-center gap-2">
                      <span>
                        {inCompare
                          ? `${compareSeries.length} plants · ${traitRight ? '2 traits, 2 axes' : '1 trait, 1 axis'}`
                          : 'Trait curves — hover to preview, click to pin'}
                      </span>
                      <span className="ms-auto d-flex flex-wrap align-items-center gap-2">
                        <span className="d-flex align-items-center gap-1">
                          <span className="small text-muted">x</span>
                          {[['das', 'DAS'], ['gdd', 'GDD']].map(([mode, label]) => (
                            <Button key={mode} size="sm" className="py-0 px-2"
                              variant={xMode === mode ? 'dark' : 'outline-secondary'}
                              onClick={() => setXMode(mode)}
                              title={mode === 'das'
                                ? 'Plant age in days after sowing'
                                : 'Aligned thermal time (one point per day; empty days are dropped, never 0)'}>
                              {label}
                            </Button>
                          ))}
                        </span>
                        <TraitSelect label="left" value={traitLeft}
                          onChange={setTraitLeft} options={traitOpts} />
                        <TraitSelect label="+ right" value={traitRight} onChange={setTraitRight}
                          options={traitOpts} allowNone />
                      </span>
                    </Card.Header>
                    <Card.Body>
                      {/* Compare mode: the plants of the export selection, one trait, ONE axis.
                          Colour carries plant identity, so the trait cannot also be
                          encoded by colour — a second trait would need a second scale,
                          and two y-scales on one chart make any crossing look meaningful
                          when it is only an artefact of the two ranges. */}
                      {inCompare ? (
                        (selectionLoading || seriesLoading) ? <Spinner animation="border" size="sm" />
                          : gddGap ? <GddGap anchor={gddAnchor} />
                          : compareRows.length === 0 ? <span className="text-muted">No observations for the selected plants</span>
                            : (
                              <>
                              <ResponsiveContainer width="100%" height={440}>
                                <LineChart data={compareRows} margin={{ top: 5, right: 30, left: 10, bottom: 8 }}
                                  onMouseMove={onChartMove} onMouseLeave={onChartLeave} onClick={onChartClick}
                                  style={{ cursor: 'pointer' }}>
                                  <CartesianGrid strokeDasharray="3 3" />
                                  <XAxis dataKey="x" type="number" ticks={dayTicks} domain={['dataMin', 'dataMax']}
                                    allowDataOverflow tickFormatter={(v) => Math.round(v)} tick={{ fontSize: 15 }}
                                    height={DAS_AXIS_HEIGHT} />
                                  <YAxis yAxisId="left" tick={{ fontSize: 15 }} width={92} tickFormatter={tickFmtLeft}
                                    label={{ value: traitLeft, angle: -90, position: 'insideLeft', style: { fontSize: 15 } }} />
                                  {/* Second trait, second scale. Colour is already spent on
                                      plant identity, so the trait is carried by line style
                                      (solid/dashed) and spelled out under the chart — and
                                      because the two scales are independent, a crossing of a
                                      solid and a dashed line means nothing. */}
                                  {traitRight && (
                                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 15 }} width={92}
                                      tickFormatter={tickFmtRight}
                                      label={{ value: traitRight, angle: 90, position: 'insideRight', style: { fontSize: 15 } }} />
                                  )}
                                  {/* Crosshair only — the numbers live in the readout strip
                                      below, where they cannot cover the curve. */}
                                  <Tooltip content={() => null} cursor={{ stroke: '#adb5bd', strokeDasharray: '3 3' }} />
                                  <Legend wrapperStyle={{ fontSize: 14, cursor: 'pointer' }}
                                    onClick={(e) => {
                                      const hit = compareSeries.find((s) => s.key === e.dataKey);
                                      if (hit) setFocusId(hit.plant.plant_id);
                                    }} />
                                  {/* yAxisId is required: this chart declares only "left"/"right",
                                      so a ReferenceLine without one looks up the default id "0",
                                      finds no axis and throws (recharts useYAxisOrThrow) — which
                                      took down the whole page on the pin click. */}
                                  {pinnedX != null && (
                                    <ReferenceLine yAxisId="left" x={pinnedX} stroke="#000" strokeDasharray="5 3" strokeWidth={1.5} />
                                  )}
                                  {compareSeries.map((s) => (
                                    <Line key={s.key} yAxisId="left" type="monotone" dataKey={s.key} stroke={s.color}
                                      name={plantLabel(s.plant)} isAnimationActive={false} connectNulls
                                      strokeWidth={s.plant.plant_id === focusId ? 2.5 : 1.2}
                                      dot={s.plant.plant_id === focusId ? compareDot(s.color) : false} />
                                  ))}
                                  {/* legendType none: the legend names plants, and 2 traits x
                                      8 plants would make it 16 rows of the same names. */}
                                  {traitRight && compareSeries.map((s) => (
                                    <Line key={s.keyR} yAxisId="right" type="monotone" dataKey={s.keyR}
                                      stroke={s.color} strokeDasharray="5 3" legendType="none"
                                      name={`${plantLabel(s.plant)} · ${traitRight}`}
                                      isAnimationActive={false} connectNulls dot={false}
                                      strokeWidth={s.plant.plant_id === focusId ? 2.5 : 1.2} />
                                  ))}
                                  <Brush dataKey="x" height={22} stroke="#8884d8" travellerWidth={8}
                                    {...(brushForce ? { startIndex: brushForce.start, endIndex: brushForce.end } : {})}
                                    tickFormatter={(v) => Math.round(v)}
                                    onChange={onBrushChange} />
                                </LineChart>
                              </ResponsiveContainer>
                              <AxisTitle text={xTitle} />
                              </>
                            )
                      ) : obsQ.isLoading ? <Spinner animation="border" size="sm" />
                        : gddGap ? <GddGap anchor={gddAnchor} />
                        : chartData.length === 0 ? <span className="text-muted">No observations</span>
                          : (
                            <>
                            <ResponsiveContainer width="100%" height={440}>
                              <LineChart data={chartData} margin={{ top: 5, right: 30, left: 10, bottom: 8 }}
                                onMouseMove={onChartMove} onMouseLeave={onChartLeave} onClick={onChartClick}
                                style={{ cursor: 'pointer' }}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="x" type="number" ticks={dayTicks} domain={['dataMin', 'dataMax']}
                                  allowDataOverflow tickFormatter={(v) => Math.round(v)} tick={{ fontSize: 15 }}
                                  height={DAS_AXIS_HEIGHT} />
                                <YAxis yAxisId="left" tick={{ fontSize: 15 }} width={92}
                                  tickFormatter={tickFmtLeft}
                                  label={{ value: traitLeft, angle: -90, position: 'insideLeft', style: { fontSize: 15 } }} />
                                {traitRight && (
                                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 15 }} width={92}
                                    tickFormatter={tickFmtRight}
                                    label={{ value: traitRight, angle: 90, position: 'insideRight', style: { fontSize: 15 } }} />
                                )}
                                <Tooltip content={() => null} cursor={{ stroke: '#adb5bd', strokeDasharray: '3 3' }} />
                                <Legend wrapperStyle={{ fontSize: 15 }} />
                                {pinnedX != null && (
                                  <ReferenceLine yAxisId="left" x={pinnedX} stroke="#000" strokeDasharray="5 3" strokeWidth={1.5} />
                                )}
                                <Line yAxisId="left" type="monotone" dataKey={traitLeft} stroke={TRAIT_COLORS[0]}
                                  dot={dot} name={traitLeft} isAnimationActive={false} connectNulls={false} />
                                {traitRight && (
                                  <Line yAxisId="right" type="monotone" dataKey={traitRight} stroke={TRAIT_COLORS[1]}
                                    dot={false} name={traitRight} isAnimationActive={false} connectNulls={false} />
                                )}
                                <Brush dataKey="x" height={22} stroke="#8884d8" travellerWidth={8}
                                  {...(brushForce ? { startIndex: brushForce.start, endIndex: brushForce.end } : {})}
                                  tickFormatter={(v) => Math.round(v)}
                                  onChange={onBrushChange} />
                              </LineChart>
                            </ResponsiveContainer>
                            <AxisTitle text={xTitle} />
                            </>
                          )}
                      {/* Fixed readout: same place every time, outside the plot area. */}
                      <div className="d-flex flex-wrap align-items-baseline gap-2 mt-2 px-1 py-1 border-top border-bottom"
                        style={{ minHeight: 34, fontSize: '0.9rem' }}>
                        {readout ? (
                          <>
                            <strong>DAS {readout.das}</strong>
                            <span className="text-muted">{readout.datetime}</span>
                            {readout.qc ? qcBadge(readout.qc) : null}
                            {readout.pinned && <Badge bg="secondary">📌 pinned</Badge>}
                            {readout.items.map((it) => (
                              <span key={it.label} className="ms-2">
                                <span style={{ color: it.color }}>{it.dashed ? '╌' : '▬'}</span>{' '}
                                <span className="text-muted">{it.label}</span>{' '}
                                <strong>{fmtValue(it.v)}</strong>
                              </span>
                            ))}
                          </>
                        ) : (
                          <span className="text-muted">
                            Hover the curve to read values here; click to pin a single-plant image.
                          </span>
                        )}
                      </div>
                      {!inCompare && (
                        <div className="small text-muted mt-2">
                          QC status: {['verified', 'auto', 'no'].filter((s) => qcCounts[s]).map((s) => (
                            <span key={s} className="me-3">{qcBadge(s)} {QC_LABELS[s]} ({qcCounts[s]})</span>
                          ))}
                        </div>
                      )}
                      {/* A legend, not a paragraph: the same four facts as symbols, in the
                          order they are looked up. Colour carries plant identity, so QC has
                          to be a marker shape. */}
                      {inCompare && (
                        <div className="small text-muted mt-2">
                          <span className="me-3"><strong>▬</strong> focused (images beside) · click legend to change</span>
                          <span className="me-3">● verified · ○ not verified</span>
                          <span className="me-3">colour = plant</span>
                          {traitRight && (
                            <span>
                              solid = {traitLeft} (left axis) · dashed = {traitRight} (right axis);
                              two scales, so a crossing means nothing
                            </span>
                          )}
                        </div>
                      )}
                      <div className="small text-muted">
                        <span className="me-3">
                          {dailyMean ? '1 point = daily mean (outlying images hidden)' : '1 point = 1 single-plant image (raw)'}
                          {gddMode ? ' · x = GDD accumulated hourly (bilinear/24); days with no environment record drop out, never 0' : ''}
                        </span>
                        <span className="me-3">axis label = CSV column</span>
                        <span>size traits in px (no calibration)</span>
                      </div>

                      {/* DAS window: drag the brush above, or type bounds. Read-only, in-browser.
                          It is the *picking* end of the window — the export form owns the
                          sampling recipe. The statistics here are therefore not the CSV's
                          numbers: every frame in view counts, including pre-QC ones, whereas
                          the export takes one frame per day at a chosen hour and filters QC.
                          Said in the caption, because two means of "the same window" that
                          differ silently is exactly the trap. */}
                      {winSummary && (
                        <div className="border rounded p-2 mt-2 bg-light">
                          <div className="d-flex align-items-center flex-wrap gap-2 mb-2">
                            <strong className="small" title="Scopes the statistics below and can be carried into the export form">
                              Time window
                            </strong>
                            <span className="d-flex align-items-center gap-1">
                              <span className="small text-muted">DAS</span>
                              <Form.Control size="sm" type="number" style={{ width: 74 }} value={winSummary.dasFrom}
                                onChange={(e) => setWindowBound('from')(e.target.value)} />
                              <span className="small">–</span>
                              <Form.Control size="sm" type="number" style={{ width: 74 }} value={winSummary.dasTo}
                                onChange={(e) => setWindowBound('to')(e.target.value)} />
                            </span>
                            <span className="text-muted small">{winSummary.dateFrom} → {winSummary.dateTo} · {winSummary.n} images</span>
                            <span className="ms-auto d-flex gap-2">
                              <Button size="sm" variant="outline-secondary" onClick={resetWindow} disabled={isFullWindow}>Reset</Button>
                              <Button size="sm" variant={analysisWindow && analysisWindow.das_min === winSummary.dasFrom && analysisWindow.das_max === winSummary.dasTo ? 'success' : 'outline-primary'}
                                onClick={useAsAnalysisWindow} disabled={isFullWindow}
                                title={isFullWindow ? 'Select a sub-range first' : 'Carry this DAS window into the export form'}>
                                Use as export window
                              </Button>
                            </span>
                          </div>
                          {/* The one line that keeps the two windows from being read as the
                              same number: this panel is the visual picker plus a read of the
                              raw series; the recipe (which frame of each day, which QC states,
                              how far merged) is applied by the export, not here. */}
                          <details>
                            <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }} className="text-muted">
                              Values in this window
                              {inCompare ? ` (${winSummary.traits.length} series)` : ''}
                            </summary>
                          <div className="text-muted mt-1 mb-1" style={{ fontSize: '0.78rem' }}>
                            Every single-plant image in the window counts here, pre-QC ones included. The export
                            applies its own recipe (one image per day, QC filter, merge level), so
                            these are a read of the raw series — not the CSV&apos;s values.
                          </div>
                          <Table size="sm" borderless className="mb-0 small">
                            <thead>
                              <tr className="text-muted">
                                <th />
                                {inCompare && (
                                  <th title={dailyMean
                                    ? 'days plotted in the window (each is the mean of that day\'s images)'
                                    : 'single-plant images plotted in the window'}>
                                    {dailyMean ? 'days' : 'n'}
                                  </th>
                                )}
                                <th>mean</th><th>min</th><th>max</th><th>first</th><th>last</th><th>Δ</th>
                                {inCompare && (
                                  <th title="QC state of the underlying single-plant images in the window (not of the plotted points)">
                                    QC images
                                  </th>
                                )}
                              </tr>
                            </thead>
                            {/* In compare mode this is one row per plant: the numbers that say
                                how much the plants differ, and the named channel that keeps
                                identity off colour alone. */}
                            <tbody>
                              {winSummary.traits.map((row) => row.stat && (
                                <tr key={row.key}>
                                  <td>
                                    <span style={{ color: row.color }}>
                                      {inCompare ? (row.dashed ? '╌ ' : '▬ ') : ''}
                                    </span>
                                    <span style={{ color: inCompare ? undefined : row.color }}>{row.key}</span>
                                  </td>
                                  {inCompare && <td>{row.n}</td>}
                                  <td>{fmtValue(row.stat.mean)}</td>
                                  <td>{fmtValue(row.stat.min)}</td>
                                  <td>{fmtValue(row.stat.max)}</td>
                                  <td>{fmtValue(row.stat.first)}</td>
                                  <td>{fmtValue(row.stat.last)}</td>
                                  <td>{(row.stat.last - row.stat.first >= 0 ? '+' : '') + fmtValue(row.stat.last - row.stat.first)}</td>
                                  {inCompare && (
                                    <td>
                                      {(() => {
                                        const states = ['verified', 'auto', 'no'].filter((q) => row.qc?.[q]);
                                        return states.map((q) => (
                                          <span key={q} className="me-1">
                                            {qcBadge(q)}{states.length > 1 ? ` ${row.qc[q]}` : ''}
                                          </span>
                                        ));
                                      })()}
                                    </td>
                                  )}
                                </tr>
                              ))}
                            </tbody>
                          </Table>
                          </details>
                        </div>
                      )}
                    </Card.Body>
                  </Card>
                </Col>

                <Col lg={6} xl={5}>
                  <Card className="h-100">
                    <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                      <span>
                        {inGrid
                          ? `Single-plant images — ${gridTiles.length} plants`
                          : inCompare && focusPlant ? `Single-plant image — ${plantLabel(focusPlant)}` : 'Single-plant image'}
                        {prefetch.total > 0 && prefetch.done < prefetch.total && (
                          <span className="text-muted small ms-2">· preloading {prefetch.done}/{prefetch.total}…</span>
                        )}
                        {showOverlay && ovPrefetch.total > 0 && ovPrefetch.done < ovPrefetch.total && (
                          <span className="text-muted small ms-2">· overlays {ovPrefetch.done}/{ovPrefetch.total}…</span>
                        )}
                      </span>
                      <Form.Check type="switch" id="seg-overlay-switch" label="Segmentation overlay"
                        checked={showOverlay && (inGrid ? gridTiles.some((t) => t.hasOverlays) : hasOverlays)}
                        disabled={inGrid ? !gridTiles.some((t) => t.hasOverlays) : !hasOverlays}
                        onChange={(e) => setShowOverlay(e.target.checked)}
                        title={hasOverlays ? '' : 'Overlays not generated for this plant yet'} />
                    </Card.Header>
                    {/* Grid controls live in this panel because the grid lives in this panel:
                        one place decides what the image area shows. */}
                    {inCompare && (
                      <Card.Header className="d-flex flex-wrap align-items-center gap-2 py-1">
                        <Form.Check type="switch" id="frame-grid-switch" className="small"
                          label={`Image grid (${multiPlants.length})`}
                          checked={gridOn} onChange={(e) => setGridOn(e.target.checked)} />
                        {gridOn && (
                          <>
                            <span className="d-flex align-items-center gap-1">
                              <span className="small text-muted">cols</span>
                              {[1, 2, 3, 4].map((c) => (
                                <Button key={c} size="sm" variant={gridCols === c ? 'dark' : 'outline-secondary'}
                                  className="py-0 px-2" onClick={() => setGridCols(c)}
                                  title={`${c} per row → ${Math.ceil(gridTiles.length / c)} row(s)`}>
                                  {c}
                                </Button>
                              ))}
                            </span>
                            <span className="d-flex align-items-center gap-1 ms-auto">
                              <Button size="sm" variant="outline-secondary" className="py-0 px-2"
                                onClick={() => setDayOverride(Math.floor((gridTargetX ?? 0)) - 1)}>◀</Button>
                              <Badge bg="dark" title="target DAS the tiles are matched to">
                                DAS {gridTargetX == null ? '—' : gridTargetX.toFixed(1)}
                              </Badge>
                              <Button size="sm" variant="outline-secondary" className="py-0 px-2"
                                onClick={() => setDayOverride(Math.floor((gridTargetX ?? 0)) + 1)}>▶</Button>
                              {dayOverride != null && (
                                <Button variant="link" size="sm" className="py-0 text-decoration-none"
                                  onClick={() => setDayOverride(null)}>follow curve</Button>
                              )}
                            </span>
                          </>
                        )}
                      </Card.Header>
                    )}
                    <Card.Body>
                      {/* Grid mode: every compared plant's frame at the same DAS, inside this
                          same panel. Tiles fill equal grid cells — no maximum width, so they
                          shrink to the column instead of sitting centred in empty space, and
                          equal cells still mean equal magnification (every crop is 600x600). */}
                      {inGrid ? (
                        <>
                          {/* Capped and scrollable: at 1 column with several plants the tiles
                              would otherwise push the curve — the thing that drives them —
                              off the screen. */}
                          <div style={{
                            display: 'grid',
                            gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))`,
                            gap: 8,
                            maxHeight: '72vh',
                            overflowY: 'auto',
                          }}>
                            {gridTiles.map((t) => (
                              <div key={t.plant.plant_id}
                                style={{
                                  minWidth: 0,
                                  border: t.plant.plant_id === focusId ? '2px solid #212529' : '2px solid transparent',
                                  borderRadius: 4,
                                  padding: 3,
                                }}>
                                <div className="small text-truncate" style={{ borderLeft: `5px solid ${t.color}`, paddingLeft: 5 }}>
                                  {plantLabel(t.plant)}
                                </div>
                                {t.loading && <Spinner animation="border" size="sm" />}
                                {t.error && <div className="small text-warning">{t.error}</div>}
                                {!t.loading && !t.error && !t.frame && (
                                  <div className="small text-muted">No image with a DAS</div>
                                )}
                                {t.frame && (
                                  <>
                                    <FrameStage plantId={t.plant.plant_id} stem={t.frame.stem}
                                      showOverlay={showOverlay && t.hasOverlays} square />
                                    <div className="text-muted" style={{ fontSize: '0.78rem', lineHeight: 1.3 }}>
                                      DAS {t.frame.day_after_sewing}
                                      {gridTargetX != null && Math.abs(t.frame.x - gridTargetX) >= 0.5 && (
                                        <span className="text-danger"> (nearest avail.)</span>
                                      )}
                                      {' · '}{t.frame.ts ? `${t.frame.ts.slice(4, 6)}-${t.frame.ts.slice(6, 8)} ${t.frame.ts.slice(8, 10)}:${t.frame.ts.slice(10, 12)}` : '—'}
                                      {t.frame.qc_status ? <> {' '}{qcBadge(t.frame.qc_status)}</> : null}
                                      {showOverlay && !t.hasOverlays && <span className="text-warning"> · no overlay</span>}
                                    </div>
                                  </>
                                )}
                              </div>
                            ))}
                          </div>
                          <details className="small text-muted mt-2">
                            <summary style={{ cursor: 'pointer' }}>
                              Each tile is that plant&apos;s single-plant image nearest DAS {gridTargetX == null ? '—' : gridTargetX.toFixed(1)}
                              {' '}· equal tiles = equal magnification
                            </summary>
                            <div className="mt-1">
                              Plants of different batches were photographed on different calendar days,
                              so DAS (age) is the comparable axis and each tile states the image it
                              actually got — “nearest” is not “identical”. All crops are 600×600 px, so
                              tiles at equal size are at equal magnification and size differences between
                              tiles are real. The dark outline marks the focused plant (thick line on the
                              curve). Hover or click the curve to move every tile together.
                            </div>
                          </details>
                        </>
                      ) : framesQ.isLoading ? <Spinner animation="border" size="sm" />
                        : framesQ.isError ? <Alert variant="warning" className="mb-0">Single-plant images are not mounted (set CROPS_DIR in platform/.env).</Alert>
                          : frames.length === 0 ? <span className="text-muted">No images</span>
                            : (
                              <>
                                {shownStem && (
                                  <>
                                    <FrameStage plantId={imagePlantId} stem={shownStem} showOverlay={showOverlay && hasOverlays} height={400} />
                                    <div className="text-center mt-1">
                                      {hoverStem ? (
                                        <span className="text-primary">Preview (hover)</span>
                                      ) : pinnedStem ? (
                                        <span>
                                          <span className="fw-semibold">📌 Pinned</span>
                                          <Button variant="link" size="sm" className="p-0 ms-2 text-decoration-none"
                                            onClick={() => setPinnedStem(null)}>clear</Button>
                                        </span>
                                      ) : <span className="text-muted">Latest image</span>}
                                      <div className="text-muted small text-truncate">{shownStem}</div>
                                    </div>
                                    {showOverlay && hasOverlays && (
                                      <div className="text-center small mt-1 text-muted">
                                        <span className="me-2"><span style={{ color: '#2ca02c' }}>▬</span> owned</span>
                                        <span className="me-2"><span style={{ color: '#d62728' }}>▭</span> rejected</span>
                                        <span className="me-2"><span style={{ color: '#1f77b4' }}>●</span> base</span>
                                        <span><span style={{ color: '#ff7f0e' }}>●</span> tip</span>
                                      </div>
                                    )}
                                  </>
                                )}
                              </>
                            )}
                    </Card.Body>
                  </Card>
                </Col>
              </Row>

            </>
          )}
        </Col>
      </Row>

      {/* The export selection lives at the foot of the page: it is the deliberate
          step after reading the curve and the frames, and as a wide table at the top
          it pushed both of them down. */}
      {/* The export selection as a table, one row per plant. A list of business keys reads
          fine at three plants and badly at fifteen; picking outliers out of several
          cultivars means scanning a column, so the columns exist. Rows beyond the colour
          budget say they are not plotted rather than looking selected-but-absent. */}
      {comparisonItems.length > 0 && (
        <Card className="mb-3">
          <Card.Header className="d-flex flex-wrap align-items-center gap-2 py-2">
            <strong className="small">
              Export selection — {selectedPlants.length} plant{selectedPlants.length === 1 ? '' : 's'}
              {comparisonItems.length !== selectedPlants.length
                && ` from ${comparisonItems.length} row${comparisonItems.length === 1 ? '' : 's'}`}
            </strong>
            {selectionLoading && <Spinner animation="border" size="sm" />}
            {analysisWindow ? (
              <span>
                <Badge bg="dark">window DAS {analysisWindow.das_min}–{analysisWindow.das_max}</Badge>
                <Button variant="link" size="sm" className="p-0 ms-1 text-decoration-none" onClick={clearAnalysisWindow}
                  title="Clear the window (export the full range)">✕</Button>
              </span>
            ) : <span className="text-muted small">full DAS range</span>}
            <span className="ms-auto d-flex flex-wrap gap-2">
              <Form.Check type="switch" id="compare-switch" className="small"
                label="Compare on chart" checked={compareOn}
                onChange={(e) => setCompareOn(e.target.checked)}
                title="Plot every plant of the selection on one axis for the chosen trait" />
              <Button size="sm" variant="primary" onClick={goToExport}>
                Export ({selectedPlants.length}) →
              </Button>
              <Button size="sm" variant="outline-secondary" onClick={clearComparison}>Clear all</Button>
            </span>
          </Card.Header>
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            <Table size="sm" hover className="mb-0 small align-middle">
              <thead>
                <tr className="text-muted">
                  <th style={{ width: 28 }} title="colour used on the chart" />
                  <th>batch</th><th>cultivar</th><th>treatment</th><th>rep</th>
                  <th title="single-plant images in the database">images</th>
                  <th style={{ width: 150 }} />
                </tr>
              </thead>
              <tbody>
                {selectedPlants.map((p) => {
                  const series = compareSeries.find((x) => x.plant.plant_id === p.plant_id);
                  const plotted = !!series;
                  return (
                    <tr key={p.plant_id} className={p.plant_id === focusId && plotted ? 'table-active' : undefined}>
                      <td>
                        {plotted
                          ? <span style={{ color: series.color, fontSize: '1.1rem' }}>▬</span>
                          : <span className="text-muted" title="not plotted (colour budget is 8 plants)">·</span>}
                      </td>
                      <td>{p.batch_code}</td>
                      <td className="text-nowrap">{p.cultivar_code}</td>
                      <td>{p.treatment_code || '—'}</td>
                      <td>{p.replicate_code}</td>
                      <td>{p.total_raspi ?? '—'}</td>
                      <td className="text-end">
                        {plotted && (
                          <Button size="sm" variant={p.plant_id === focusId ? 'dark' : 'outline-secondary'}
                            className="py-0 px-2 me-1" onClick={() => setFocusId(p.plant_id)}
                            title="Show this plant's images and mark it on the curve">focus</Button>
                        )}
                        <Button size="sm" variant="outline-danger" className="py-0 px-2"
                          title="Remove this plant from the selection"
                          onClick={() => removePlant(p)}>✕</Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </div>
          {(selectionNote || droppedPlants > 0) && (
            <div className="px-3 py-2 small text-danger border-top">
              {selectionNote && (
                <div>
                  {selectionNote}
                  <Button variant="link" size="sm" className="py-0 text-decoration-none"
                    onClick={() => setSelectionNote(null)}>dismiss</Button>
                </div>
              )}
              {droppedPlants > 0 && (
                <div>
                  {selectedPlants.length} plants selected; the first {MAX_COMPARE} are plotted
                  (ordered by batch, cultivar, treatment, replicate). The other {droppedPlants} are
                  still exported — colour cannot carry more than {MAX_COMPARE} identities.
                </div>
              )}
            </div>
          )}
        </Card>
      )}
    </Container>
  );
}
