import React, { useState, useEffect } from 'react';
import { fetchCultivarSignatureTraits } from '../services/queryServiceV2';

// Cultivar-level trait profile: the five signature traits, one row per batch.
// Everything here comes from the Raspberry Pi top-view RGB series (the same
// source as the growth curves), so all batches are covered and every value has
// biological replicates behind it. The DSLR colour/texture measurements are
// deliberately not mixed in — single shot, one batch only, no replicates.
//
// The sampling recipe (which days, which frame of each day, how far merged) comes
// from the API and is the same recipe the CSV export uses, so these numbers are
// the numbers in the downloaded file. It is printed in the caption because it is
// not recoverable from the values.

const TRAITS = [
  {
    key: 'leaf_count',
    label: 'Leaf number',
    short: 'Leaves',
    unit: '',
    formula: 'Segmented leaf instances owned by this plant',
    note: 'Cotyledons are still counted.',
    digits: 1,
  },
  {
    key: 'leaf_area',
    label: 'Leaf area',
    short: 'Leaf area',
    unit: 'px',
    formula: 'Projected leaf area = foreground pixels of the ownership-filtered mask',
    note: 'In pixels — not calibrated to cm².',
    digits: 0,
  },
  {
    key: 'circularity_2',
    label: 'Circularity',
    short: 'Circularity',
    unit: '',
    formula: 'Circularity₂ = 4π × Area / Perimeter²',
    note: '1 = perfect circle; lower = more elongated or dissected.',
    digits: 3,
  },
  {
    key: 'anthocyanin_chroma_basic',
    label: 'Anthocyanin index',
    short: 'Anthocyanin',
    unit: '',
    formula: 'AC_CB = (R + B) / G',
    note: 'Colour proxy, higher = more anthocyanin. Not a concentration measurement.',
    digits: 2,
  },
  {
    key: 'glcm_contrast',
    label: 'Texture contrast',
    short: 'Texture',
    unit: '',
    formula: 'GLCM contrast over the leaf ROI',
    note: 'Surface/vein coarseness; sensitive to illumination.',
    digits: 2,
  },
];

// "36;37;38;39" -> "36-39", "28;30;32;34" -> "28,30,32,34". A contiguous run is
// collapsed because that is the common case and the cell is narrow; the full list
// is always in the title attribute.
const formatDas = (das) => {
  const days = String(das || '').split(';').filter(Boolean).map(Number);
  if (!days.length) return '—';
  const contiguous = days.every((d, i) => i === 0 || d === days[i - 1] + 1);
  return contiguous && days.length > 1 ? `${days[0]}-${days[days.length - 1]}` : days.join(',');
};

const fmt = (v, digits) => {
  if (v == null || !isFinite(v)) return '—';
  return digits === 0 ? Math.round(v).toLocaleString() : v.toFixed(digits);
};

const cell = {
  border: '1px solid #ddd',
  // Eight columns at the page's 20 px body size only just fit the profile column,
  // so the horizontal padding is tighter here than in the identity tables.
  padding: '5px 7px',
  textAlign: 'left',
  whiteSpace: 'nowrap',
  lineHeight: 1.35,
};

const headCell = {
  ...cell,
  backgroundColor: '#e9ecef',
  fontWeight: 'bold',
  verticalAlign: 'bottom',
};

const CultivarSignatureTraits = ({ cultivarId }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const result = await fetchCultivarSignatureTraits(cultivarId);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError('Failed to load signature traits.');
        console.error(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [cultivarId]);

  if (loading) return <p>Loading signature traits...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;
  if (!data || !data.batches || data.batches.length === 0) {
    return <p>No trait data available for this cultivar.</p>;
  }

  return (
    <div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={headCell}>Batch</th>
              {/* Window and replicate count share one column: five trait columns
                  plus three context columns overflow the profile column. */}
              <th
                style={headCell}
                title="The imaging days actually averaged for this batch, and the replicates behind the mean (human-verified / total)"
              >
                Days<br /><span style={{ fontWeight: 'normal' }}>(DAS, n)</span>
              </th>
              {TRAITS.map((t) => (
                <th key={t.key} style={headCell} title={`${t.label} — ${t.formula}`}>
                  {t.short || t.label}
                  {t.unit ? <><br /><span style={{ fontWeight: 'normal' }}>({t.unit})</span></> : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.batches.map((b) => (
              <tr key={b.batch_code}>
                <td style={cell}>{b.batch_code}</td>
                {b.status === 'ok' ? (
                  <>
                    <td style={cell} title={`DAS ${(b.das_used || '').split(';').join(', ')}`}>
                      {formatDas(b.das_used)}
                      <span style={{ color: '#6c757d' }}>
                        {', '}{b.n_verified}/{b.n_replicates}
                      </span>
                    </td>
                    {TRAITS.map((t) => {
                      const v = b.values[t.key] || {};
                      return (
                        <td key={t.key} style={cell}>
                          {fmt(v.mean, t.digits)}
                          <span style={{ color: '#6c757d' }}>
                            {' ± '}{fmt(v.sd, t.digits)}
                          </span>
                        </td>
                      );
                    })}
                  </>
                ) : (
                  <td style={{ ...cell, color: '#6c757d' }} colSpan={1 + TRAITS.length}>
                    Not reprocessed yet — observations for this batch are still pre-QC
                    ({b.plant_count} plant{b.plant_count === 1 ? '' : 's'}).
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* The definitions are needed to read the table honestly but are read once,
          not on every visit — and eight lines of small print here push the growth
          curves off the screen (and out of a figure made from this page). Collapsed by
          default, with the two facts you cannot omit kept in the summary line.
          Column headers carry the same formulas as title tooltips. */}
      <details style={{ marginTop: 10, fontSize: '0.88rem', color: '#6c757d', lineHeight: 1.6 }}>
        <summary style={{ cursor: 'pointer' }}>
          mean ± 1 SD across replicates, Raspberry Pi top-view RGB
          <span style={{ fontStyle: 'italic' }}> — trait definitions and QC notes</span>
        </summary>
        <div style={{ marginTop: 6 }}>
          <strong>Values</strong> are mean ± 1 SD across biological replicates on the
          reference day (each replicate is first reduced to its daily mean); the
          <em> (DAS, n)</em> column gives that day and how many of the replicates are
          human-verified. Only QC-correct observations count — <em>auto</em> = model
          leaf ownership, <em>verified</em> = human-reviewed.
        </div>
        <div>
          <strong>Source</strong>: Raspberry Pi top-view RGB, same series as the growth
          curves below. Not comparable with the G111 DSLR colour/texture measurements
          (different camera, optics and lighting) — do not mix the two.
        </div>
        <div style={{ marginTop: 4 }}>
          {TRAITS.map((t) => (
            <div key={t.key}>
              <strong>{t.label}</strong>: {t.formula}. {t.note}
            </div>
          ))}
        </div>
      </details>
    </div>
  );
};

export default CultivarSignatureTraits;
