import React, { useState, useEffect } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { fetchCultivarTimeSeriesData } from '../services/queryServiceV2';
import { yTickWidth, yAxisTitleStyle } from './charts/axisSpace';

// Chart typography: recharts' 12 px defaults are unreadably small next to the page's
// 20 px body text (and the users run the browser at 90% zoom).
const TICK_FONT = 16;
const AXIS_TITLE_FONT = 16;
const yTickFormat = (v) => (v == null ? '' : Math.round(v).toLocaleString());

// Width the y-axis has to reserve for the numbers in these aggregates.
const tickWidthFor = (aggs) => yTickWidth({
  values: aggs.flatMap(({ rows }) => rows.flatMap((r) => (r.band ? r.band : [r.mean]))),
  fontSize: TICK_FONT,
  format: yTickFormat,
});

// Cultivar-level growth view: within a batch, show the biological replicates as a
// mean ± 1 SD band (dispersion) with an optional overlay of the individual
// replicate curves. Aggregation is by integer DAS (days after sowing): first each
// replicate is reduced to a per-day mean, then across replicates we take the mean
// and sample SD. The band expresses replicate spread — it is NOT a significance
// test (repeated measures on the same plant are correlated; overlap says nothing).

const TRAITS = [
  { key: 'leaf_area', title: 'Leaf area over time', yLabel: 'Leaf area (px)', mean: '#2ca25f', band: '#2ca25f' },
  { key: 'leaf_count', title: 'Leaf number over time', yLabel: 'Leaf number', mean: '#3182bd', band: '#3182bd' },
];

const REP_COLORS = ['#e6550d', '#756bb1', '#31a354', '#c51b8a', '#2b8cbe', '#dd1c77'];

const fmt = (v) => {
  if (v == null || !isFinite(v)) return '—';
  return Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : v.toFixed(1);
};

// Reduce one batch's trait data { rep1: [points], rep2: [...] } to a per-DAS
// array with mean/sd/band across replicates plus each replicate's daily mean.
const aggregateBatchTrait = (repMap) => {
  const repKeys = Object.keys(repMap).sort();
  const repDaily = {}; // rep -> { das -> daily mean }

  repKeys.forEach((rep) => {
    const byDay = {};
    (repMap[rep] || []).forEach((pt) => {
      const v = parseFloat(pt.value);
      if (!isFinite(v)) return;
      const das = pt.days_after_planting_int;
      if (das == null) return;
      (byDay[das] = byDay[das] || []).push(v);
    });
    repDaily[rep] = {};
    Object.entries(byDay).forEach(([das, vals]) => {
      repDaily[rep][das] = vals.reduce((a, b) => a + b, 0) / vals.length;
    });
  });

  const dasSet = new Set();
  repKeys.forEach((rep) => Object.keys(repDaily[rep]).forEach((d) => dasSet.add(Number(d))));
  const dasList = [...dasSet].sort((a, b) => a - b);

  const rows = dasList.map((das) => {
    const vals = repKeys
      .map((rep) => repDaily[rep][das])
      .filter((v) => v != null && isFinite(v));
    const n = vals.length;
    const mean = n ? vals.reduce((a, b) => a + b, 0) / n : null;
    let sd = 0;
    if (n >= 2) {
      const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1);
      sd = Math.sqrt(variance);
    }
    const row = {
      das,
      n,
      sd,
      mean,
      band: mean == null ? null : [mean - sd, mean + sd],
    };
    repKeys.forEach((rep) => { row[rep] = repDaily[rep][das] ?? null; });
    return row;
  });

  return { rows, repKeys };
};

const BandTooltip = ({ active, payload }) => {
  if (!active || !payload || !payload.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div style={{
      background: '#fff', border: '1px solid #ccc', borderRadius: 4,
      padding: '6px 10px', fontSize: '0.9rem',
    }}>
      <div style={{ fontWeight: 600 }}>Day {row.das}</div>
      <div>Mean: {fmt(row.mean)} ± {fmt(row.sd)} SD</div>
      <div style={{ color: '#6c757d' }}>n = {row.n} replicate{row.n === 1 ? '' : 's'}</div>
    </div>
  );
};

const CultivarPlots = ({ cultivarId }) => {
  const [plotData, setPlotData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showReps, setShowReps] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        setLoading(true);
        const data = await fetchCultivarTimeSeriesData(cultivarId);
        if (!cancelled) setPlotData(data);
      } catch (err) {
        if (!cancelled) setError('Failed to load plot data.');
        console.error(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchData();
    return () => { cancelled = true; };
  }, [cultivarId]);

  if (loading) return <p>Loading plots...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;
  if (!plotData || Object.keys(plotData).length === 0) {
    return <p>No plot data available for this cultivar.</p>;
  }

  // Group the flat "cultivar-replicate-batch" keys into { batch: { leaf_count, leaf_area } },
  // where each trait maps rep label -> point array.
  const grouped = {};
  Object.keys(plotData).forEach((key) => {
    const [, replicate, batch] = key.split('-');
    if (!grouped[batch]) grouped[batch] = { leaf_count: {}, leaf_area: {} };
    grouped[batch].leaf_count[`rep${replicate}`] = plotData[key].leaf_count;
    grouped[batch].leaf_area[`rep${replicate}`] = plotData[key].leaf_area;
  });
  const batches = Object.keys(grouped).sort();
  const aggsByBatch = {};
  batches.forEach((b) => {
    aggsByBatch[b] = TRAITS.map((trait) => aggregateBatchTrait(grouped[b][trait.key]));
  });
  // One y-axis band width for every chart on the page: leaf area needs six digits and
  // leaf number one, but charts stacked under each other have to keep their DAS axes
  // aligned, so they all reserve the width the widest number needs.
  const sharedTickWidth = tickWidthFor(Object.values(aggsByBatch).flat());

  const renderBandChart = ({ rows, repKeys }, trait, bandWidth) => {
    if (!rows.length) return <p>No data for {trait.title}.</p>;

    // This chart's own numbers may be far narrower than the page's widest (leaf number
    // vs leaf area): reserve only the band it needs and park the slack to the left of
    // the axis title, so every title hugs its own ticks and the plot areas still align.
    const tickWidth = tickWidthFor([{ rows }]);
    const titleSlack = Math.max(0, bandWidth - tickWidth);

    const minDas = Math.floor(Math.min(...rows.map((r) => r.das)));
    const maxDas = Math.ceil(Math.max(...rows.map((r) => r.das)));
    // In the narrow (half-page) column a tick per day collides — thin them out.
    const step = Math.ceil((maxDas - minDas + 1) / 14) || 1;
    const ticks = [];
    for (let i = minDas; i <= maxDas; i += step) ticks.push(i);

    return (
      <div style={{ marginBottom: 24, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <h6 style={{ textAlign: 'center', fontSize: '1.05rem' }}>{trait.title}</h6>
        {/* The y-axis title lives in its own column beside the chart rather than
            inside the axis band, so it cannot collide with the tick labels however
            wide those get. Legend on top: at the bottom the x-axis title lands on it. */}
        <div style={{ display: 'flex', width: '100%', height: 300 }}>
          <div style={yAxisTitleStyle(AXIS_TITLE_FONT, { before: titleSlack })}>{trait.yLabel}</div>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 6, right: 12, bottom: 26, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="das"
                type="number"
                domain={['dataMin', 'dataMax']}
                ticks={ticks}
                tick={{ fontSize: TICK_FONT }}
                label={{
                  value: 'Days after sowing (DAS)',
                  position: 'insideBottom',
                  offset: -18,
                  style: { fontSize: AXIS_TITLE_FONT, fill: '#666' },
                }}
              />
              <YAxis width={tickWidth} tick={{ fontSize: TICK_FONT }} tickFormatter={yTickFormat} />
              <Tooltip content={<BandTooltip />} />
              <Legend verticalAlign="top" height={24} wrapperStyle={{ fontSize: TICK_FONT }} />
              <Area
                dataKey="band"
                name="±1 SD"
                stroke="none"
                fill={trait.band}
                fillOpacity={0.2}
                connectNulls
                isAnimationActive={false}
              />
              <Line
                dataKey="mean"
                name="Mean"
                stroke={trait.mean}
                strokeWidth={2.5}
                dot={{ r: 2 }}
                connectNulls
                isAnimationActive={false}
              />
              {showReps && repKeys.map((rep, i) => (
                <Line
                  key={rep}
                  dataKey={rep}
                  name={rep}
                  stroke={REP_COLORS[i % REP_COLORS.length]}
                  strokeWidth={1}
                  strokeOpacity={0.75}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  };

  return (
    <div>
      {batches.map((batch, bi) => {
        const aggs = aggsByBatch[batch];
        return (
          // The rule separates one batch from the previous one — the first batch is
          // already separated by the card title, so it gets no rule.
          <div
            key={batch}
            style={bi === 0
              ? { marginTop: 4 }
              : { marginTop: 24, borderTop: '1px solid #eee', paddingTop: 16 }}
          >
            <h5 style={{ marginBottom: 12 }}>Batch {batch}</h5>
            {TRAITS.map((trait, i) => (
              <React.Fragment key={trait.key}>
                {renderBandChart(aggs[i], trait, sharedTickWidth)}
              </React.Fragment>
            ))}
          </div>
        );
      })}

      {/* Control and caption sit under the charts, where a figure caption belongs —
          at the top they pushed the curves themselves below the fold. */}
      <div style={{
        marginTop: 20, padding: 12, background: '#f8f9fa',
        borderRadius: 8, border: '1px solid #dee2e6',
      }}>
        <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontWeight: 600 }}>
          <input
            type="checkbox"
            checked={showReps}
            onChange={(e) => setShowReps(e.target.checked)}
            style={{ marginRight: 8, transform: 'scale(1.2)' }}
          />
          Show individual replicates
        </label>
        <div style={{ marginTop: 6, fontSize: '0.88rem', color: '#6c757d' }}>
          Shaded band = ±1 SD across biological replicates (dispersion within the batch).
          It is not a significance test — for repeated measures on the same plant, band
          overlap does not indicate (non-)significance. Toggle to overlay each replicate
          and spot outlier or failed plants.
        </div>
      </div>
    </div>
  );
};

export default CultivarPlots;
