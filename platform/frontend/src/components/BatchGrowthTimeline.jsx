import React from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ReferenceArea, ResponsiveContainer,
} from 'recharts';

// Where this cultivar's plants stayed and for how long, batch by batch, plus the
// temperature/humidity logged in that chamber during the stay. Chamber codes and
// colours come from the data — never from a hardcoded list, which is how the old
// legend ended up advertising chambers (G121–G125) that do not exist.

const CHAMBER_COLORS = {
  R141: '#8c6d31',
  R142: '#bd9e39',
  G120: '#3182bd',
  G126: '#31a354',
  G111: '#756bb1',
};
const FALLBACK_COLORS = ['#e6550d', '#756bb1', '#c51b8a', '#2b8cbe', '#636363'];

const colorFor = (code, index) =>
  CHAMBER_COLORS[code] || FALLBACK_COLORS[index % FALLBACK_COLORS.length];

const TEMP_COLOR = '#d95f02';
const RH_COLOR = '#2b8cbe';

// Left/right YAxis width in the environment chart. The residence bar above the
// chart is inset by the same amount so both span the identical date range.
const AXIS_WIDTH = 44;

const fmt1 = (v) => (v == null || !isFinite(v) ? '—' : v.toFixed(1));

const shortDate = (iso) => {
  if (!iso) return 'N/A';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
};

const cell = { border: '1px solid #ddd', padding: '8px 10px', textAlign: 'left', whiteSpace: 'nowrap' };
const headCell = { ...cell, backgroundColor: '#e9ecef', fontWeight: 'bold' };

const DAY_MS = 86400000;
const isoDay = (d) => new Date(d).toISOString().slice(0, 10);

// One row per calendar day of the batch's residence window — including days with
// no readings, which stay null. That makes the chart's x-axis span exactly the
// same window as the residence bar above it, so the two line up, and it shows the
// logger gaps as breaks in the line instead of silently compressing them away.
const buildBatchSeries = (stays) => {
  const byDate = {};
  stays.forEach((stay) => {
    (stay.environment?.daily || []).forEach((d) => {
      byDate[d.date] = {
        t_mean: d.t_mean,
        t_min: d.t_min,
        t_max: d.t_max,
        rh_mean: d.rh_mean,
      };
    });
  });

  const bounds = stays.flatMap((s) => [s.entry_date, s.exit_date]).filter(Boolean);
  if (!bounds.length) return { rows: [], spans: [], hasEnv: false };
  const min = new Date(Math.min(...bounds.map((d) => new Date(d))));
  const max = new Date(Math.max(...bounds.map((d) => new Date(d))));

  const chamberOn = (iso) => {
    const stay = stays.find(
      (s) => s.entry_date <= iso && iso <= (s.exit_date || s.entry_date),
    );
    return stay ? stay.chamber_code : null;
  };

  const rows = [];
  for (let t = min.getTime(); t <= max.getTime(); t += DAY_MS) {
    const date = isoDay(t);
    rows.push({
      date,
      chamber_code: chamberOn(date),
      t_mean: byDate[date]?.t_mean ?? null,
      t_min: byDate[date]?.t_min ?? null,
      t_max: byDate[date]?.t_max ?? null,
      rh_mean: byDate[date]?.rh_mean ?? null,
    });
  }

  const spans = stays
    .filter((s) => s.entry_date)
    .map((s) => ({
      chamber_code: s.chamber_code,
      from: s.entry_date,
      to: s.exit_date || s.entry_date,
    }));

  const hasEnv = rows.some((r) => r.t_mean != null || r.rh_mean != null);

  // Temperature axis: zoom to the data (a 0-based axis wastes half the plot on an
  // empty 0–17 °C band) but keep the ticks whole degrees and evenly spaced —
  // letting recharts round a 6 °C span itself produces gaps like 19, 21, 24.
  const temps = rows.map((r) => r.t_mean).filter((v) => v != null);
  let tDomain = [0, 1];
  let tTicks = [];
  if (temps.length) {
    const lo = Math.floor(Math.min(...temps)) - 1;
    let hi = Math.ceil(Math.max(...temps)) + 1;
    while ((hi - lo) % 4 !== 0) hi += 1;
    const step = (hi - lo) / 4;
    tDomain = [lo, hi];
    tTicks = [0, 1, 2, 3, 4].map((i) => lo + i * step);
  }

  return { rows, spans, hasEnv, tDomain, tTicks };
};

const EnvTooltip = ({ active, payload }) => {
  if (!active || !payload || !payload.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div style={{ background: '#fff', border: '1px solid #ccc', borderRadius: 4, padding: '6px 10px', fontSize: '0.9rem' }}>
      <div style={{ fontWeight: 600 }}>{row.date} · {row.chamber_code}</div>
      <div style={{ color: TEMP_COLOR }}>
        Temp {fmt1(row.t_mean)} °C <span style={{ color: '#6c757d' }}>({fmt1(row.t_min)}–{fmt1(row.t_max)})</span>
      </div>
      <div style={{ color: RH_COLOR }}>RH {fmt1(row.rh_mean)} %</div>
    </div>
  );
};

const BatchGrowthTimeline = ({ batchesData }) => {
  if (!batchesData || batchesData.length === 0) {
    return <p>No growth chamber data available</p>;
  }

  const chamberCodes = [...new Set(
    batchesData.flatMap((b) => (b.stays || []).map((s) => s.chamber_code)),
  )].sort();

  return (
    <div>
      <div style={{ marginBottom: 12, fontSize: '0.88rem', color: '#6c757d' }}>
        Chamber residence per batch, with the temperature and humidity logged in that
        chamber over the same window.
      </div>

      {/* Legend — only chambers this cultivar actually stayed in */}
      <div style={{ marginBottom: 20, display: 'flex', gap: 18, flexWrap: 'wrap' }}>
        {chamberCodes.map((code, i) => (
          <div key={code} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 18, height: 18, backgroundColor: colorFor(code, i),
              borderRadius: 3, border: '1px solid #ccc',
            }} />
            <span>{code}</span>
          </div>
        ))}
      </div>

      {batchesData.map((batch) => {
        const stays = batch.stays || [];
        const dates = stays.flatMap((s) => [s.entry_date, s.exit_date]).filter(Boolean);
        const min = dates.length ? new Date(Math.min(...dates.map((d) => new Date(d)))) : null;
        const max = dates.length ? new Date(Math.max(...dates.map((d) => new Date(d)))) : null;
        const spanDays = min && max ? Math.round((max - min) / 86400000) : 0;
        const pos = (d) => (!min || !spanDays ? 0 : ((new Date(d) - min) / 86400000 / spanDays) * 100);
        const width = (a, b) => (!spanDays || !a || !b ? 0 : ((new Date(b) - new Date(a)) / 86400000 / spanDays) * 100);
        const { rows, spans, hasEnv, tDomain, tTicks } = buildBatchSeries(stays);

        return (
          <div key={batch.batch_code} style={{ marginTop: 20, borderTop: '1px solid #eee', paddingTop: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap' }}>
              <h5 style={{ margin: 0 }}>Batch {batch.batch_code}</h5>
              <span style={{ color: '#6c757d', fontSize: '0.9rem' }}>
                {shortDate(min)} – {shortDate(max)} · {spanDays} days
              </span>
            </div>

            {/* Stay table with the environment recorded during each stay */}
            <div style={{ overflowX: 'auto', marginTop: 12 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.92rem' }}>
                <thead>
                  <tr>
                    <th style={headCell}>Facility</th>
                    <th style={headCell}>Entry → Exit</th>
                    <th style={headCell}>Days</th>
                    <th style={headCell}>Plants</th>
                    <th style={headCell}>Temp (°C)</th>
                    <th style={headCell}>RH (%)</th>
                  </tr>
                </thead>
                <tbody>
                  {stays.map((stay, idx) => {
                    const env = stay.environment;
                    const coverage = env
                      ? `${env.days_covered} days covered · ${env.n_sensors} sensor${env.n_sensors === 1 ? '' : 's'} · ${env.n_readings.toLocaleString()} readings`
                      : 'no environment readings in this window';
                    return (
                      <tr
                        key={`row-${stay.chamber_code}-${stay.entry_date}-${idx}`}
                        title={`${stay.chamber_code}${stay.facility_description ? ` (${stay.facility_description}` : ' ('}${stay.phase === 'seedling' ? ', seedlings' : ', observation individuals'}): ${stay.entry_date} → ${stay.exit_date || 'open'} — ${coverage}`}
                      >
                        <td style={cell}>
                          <span style={{
                            display: 'inline-block', width: 10, height: 10, borderRadius: 2, marginRight: 6,
                            backgroundColor: colorFor(stay.chamber_code, chamberCodes.indexOf(stay.chamber_code)),
                          }} />
                          {stay.chamber_code}
                          {stay.facility && (
                            <span style={{ color: '#6c757d' }}> · {stay.facility}</span>
                          )}
                        </td>
                        <td style={cell}>{shortDate(stay.entry_date)} → {stay.exit_date ? shortDate(stay.exit_date) : 'open'}</td>
                        <td style={cell}>{stay.days ?? '—'}</td>
                        <td style={cell}>{stay.plant_count}</td>
                        {env ? (
                          <>
                            <td style={cell}>
                              {fmt1(env.temperature.mean)}
                              <span style={{ color: '#6c757d' }}> ({fmt1(env.temperature.min)}–{fmt1(env.temperature.max)})</span>
                            </td>
                            <td style={cell}>
                              {fmt1(env.humidity.mean)}
                              <span style={{ color: '#6c757d' }}> ({fmt1(env.humidity.min)}–{fmt1(env.humidity.max)})</span>
                            </td>
                          </>
                        ) : (
                          <td style={{ ...cell, color: '#6c757d' }} colSpan={2}>
                            No environment readings
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Residence bar — inset by the chart's axis widths so its 0–100%
                maps onto the same span as the x-axis directly below it. */}
            <div style={{
              marginTop: 14,
              paddingLeft: AXIS_WIDTH - 1,
              paddingRight: AXIS_WIDTH - 1,
            }}>
              <div
                data-role="residence-bar"
                style={{
                  position: 'relative', height: 30, boxSizing: 'border-box',
                  background: '#f5f5f5', border: '1px solid #ddd', borderRadius: 4, overflow: 'hidden',
                }}
              >
                {stays.map((stay, idx) => (
                  <div
                    key={`${stay.chamber_code}-${stay.entry_date}-${idx}`}
                    title={`${stay.chamber_code}${stay.facility ? ` · ${stay.facility}` : ''}: ${stay.entry_date} → ${stay.exit_date || 'open'} · ${stay.days ?? '?'} days · ${stay.plant_count} plant(s)`}
                    style={{
                      position: 'absolute',
                      left: `${pos(stay.entry_date)}%`,
                      width: `${Math.max(width(stay.entry_date, stay.exit_date), 3)}%`,
                      top: 3, height: 22,
                      backgroundColor: colorFor(stay.chamber_code, chamberCodes.indexOf(stay.chamber_code)),
                      borderRadius: 3, color: '#fff', fontSize: 12, fontWeight: 600,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      overflow: 'hidden', whiteSpace: 'nowrap', padding: '0 4px',
                      textShadow: '1px 1px 1px rgba(0,0,0,0.4)',
                    }}
                  >
                    {stay.chamber_code} · {stay.days ?? '?'} d
                  </div>
                ))}
              </div>
            </div>

            {/* Daily environment over the same window (null on days with no readings) */}
            {hasEnv && (
              <div style={{ marginTop: 2 }}>
                <ResponsiveContainer width="100%" height={210}>
                  <ComposedChart data={rows} margin={{ top: 4, right: 0, bottom: 16, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    {spans.map((s, i) => (
                      <ReferenceArea
                        key={`${s.chamber_code}-${i}`}
                        x1={s.from}
                        x2={s.to}
                        fill={colorFor(s.chamber_code, chamberCodes.indexOf(s.chamber_code))}
                        fillOpacity={0.08}
                        ifOverflow="extendDomain"
                      />
                    ))}
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11 }}
                      minTickGap={28}
                      tickFormatter={(d) => (d ? d.slice(5) : '')}
                    />
                    {/* Fixed axis widths — the residence bar above is inset by the
                        same amount, which is what keeps the two aligned. */}
                    {/* Temperature zoomed to its own range; RH keeps the full
                        0–100 % scale it is defined on. */}
                    <YAxis
                      yAxisId="t"
                      width={AXIS_WIDTH}
                      tick={{ fontSize: 11 }}
                      domain={tDomain}
                      ticks={tTicks}
                      allowDecimals={false}
                    />
                    <YAxis
                      yAxisId="rh"
                      orientation="right"
                      width={AXIS_WIDTH}
                      tick={{ fontSize: 11 }}
                      domain={[0, 100]}
                      ticks={[0, 20, 40, 60, 80, 100]}
                    />
                    <Tooltip content={<EnvTooltip />} />
                    <Legend />
                    <Line
                      yAxisId="t" dataKey="t_mean" name="Temp °C (daily mean)"
                      stroke={TEMP_COLOR} strokeWidth={2} dot={false}
                      connectNulls={false} isAnimationActive={false}
                    />
                    <Line
                      yAxisId="rh" dataKey="rh_mean" name="RH % (daily mean)"
                      stroke={RH_COLOR} strokeWidth={2} dot={false}
                      connectNulls={false} isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        );
      })}

      <div style={{ marginTop: 16, fontSize: '0.85rem', color: '#6c757d', lineHeight: 1.6 }}>
        <div>
          Facility: <strong>Walk-in</strong> = walk-in growth chamber,
          <strong> Greenhouse</strong> = observation greenhouse. Hover a row for the
          plant records it covers (seedlings vs observation individuals) and the
          environment coverage.
        </div>
        Environment is chamber-level: all arduino sensors mounted in that chamber,
        averaged over the stay window (daily mean; the range in brackets is the
        min/max of individual readings). Gaps are real — the logger has periods with
        no data, and stays without readings are labelled rather than left blank.
      </div>
    </div>
  );
};

export default BatchGrowthTimeline;
