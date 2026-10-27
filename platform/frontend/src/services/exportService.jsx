// Structured export — the platform's hand-off point to downstream analysis.
// Every call goes to the one backend definition of the sampling recipe
// (`services/trait_export`), so the numbers on the Cultivar page, the preview
// table and the downloaded CSV are the same numbers.
import { apiV2 as api } from './api';

// A CSV can take a while to stream and is fetched as a blob rather than a plain
// link: the API is bearer-authenticated, and an <a href> cannot carry the header.
const DOWNLOAD_TIMEOUT_MS = 300_000;

// Query string for both preview and download. `scopes` is the honest selector:
// the flat batch/cultivar lists are independent filters and would cross-multiply
// (asking for s0117 in B08 and s0232 in B09 would also return B08 × s0232).
export const buildParams = ({ scopes, traits, recipe, resolution }) => {
  const p = new URLSearchParams();
  if (scopes?.length) {
    p.set('scopes', scopes.map((s) => [
      s.batch_code || '', s.cultivar_code || '', s.treatment_code || '', s.replicate_code ?? '',
    ].join('/')).join(';'));
  }
  if (traits?.length) p.set('traits', traits.join(','));
  const r = recipe || {};
  p.set('preset', r.preset || 'default');
  if (r.level) p.set('level', r.level);
  if (r.day_mode) p.set('day_mode', r.day_mode);
  if (r.day_mode === 'tail' && r.n_days) p.set('n_days', String(r.n_days));
  if (r.day_mode === 'list' && r.das_list) p.set('das_list', r.das_list);
  if (r.day_mode === 'range') {
    if (r.das_from !== '' && r.das_from != null) p.set('das_from', String(r.das_from));
    if (r.das_to !== '' && r.das_to != null) p.set('das_to', String(r.das_to));
  }
  if (r.day_mode === 'dates') {
    if (r.date_from) p.set('date_from', r.date_from);
    if (r.date_to) p.set('date_to', r.date_to);
  }
  if (r.frame_pick) p.set('frame_pick', r.frame_pick);
  if (r.frame_pick === 'nearest_hour' && r.pick_hour !== '' && r.pick_hour != null) {
    p.set('pick_hour', String(r.pick_hour));
  }
  if (r.qc_status?.length) p.set('qc_status', r.qc_status.join(','));
  if (r.require_leaves != null) p.set('require_leaves', String(r.require_leaves));
  if (r.include_gdd != null) p.set('include_gdd', String(r.include_gdd));
  if (r.gdd_anchor) p.set('gdd_anchor', r.gdd_anchor);
  if (resolution) p.set('resolution', resolution);
  return p;
};

// Everything the form needs: trait list by category, signature set, the traits
// that only exist downstream (with the reason), presets, knob domains, limits.
export const fetchExportOptions = async () => {
  const r = await api.get('/export/traits/options');
  return r.data;
};

export const fetchTraitPreview = async (args) => {
  const r = await api.get(`/export/traits/preview?${buildParams(args).toString()}`);
  return r.data;
};

export const fetchEnvironmentPreview = async (args) => {
  const r = await api.get(`/export/environment/preview?${buildParams(args).toString()}`);
  return r.data;
};

const saveBlob = (blob, name) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const filenameFrom = (headers, fallback) => {
  const cd = headers?.['content-disposition'] || '';
  const m = /filename=([^;]+)/i.exec(cd);
  return m ? m[1].trim().replace(/^"|"$/g, '') : fallback;
};

// Returns the recipe/row headers alongside the saved filename so the caller can
// show what was actually downloaded — the sampling recipe cannot be recovered
// from the file's numbers afterwards.
const download = async (path, args, fallbackName) => {
  let res;
  try {
    res = await api.get(`${path}?${buildParams(args).toString()}`, {
      responseType: 'blob',
      timeout: DOWNLOAD_TIMEOUT_MS,
    });
  } catch (err) {
    // With responseType blob the error body is a Blob too, so the backend's
    // explanation ("no QC-correct observations in this window", "exceeds the row
    // limit") would otherwise be lost and shown as a bare status code.
    const body = err?.response?.data;
    if (body instanceof Blob) {
      const text = await body.text().catch(() => '');
      let detail = text;
      try { detail = JSON.parse(text).detail ?? text; } catch { /* not JSON */ }
      if (detail) throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    throw err;
  }
  const name = filenameFrom(res.headers, fallbackName);
  saveBlob(res.data, name);
  return {
    filename: name,
    rows: res.headers['x-export-rows'],
    recipe: res.headers['x-export-recipe'],
    gdd: res.headers['x-export-gdd'],
    // Says how many plants each selection row contributed, and names the rows
    // that contributed nothing — a download can be taken without previewing.
    scopes: res.headers['x-export-scopes'],
  };
};

export const downloadTraitsCsv = (args) => download('/export/traits.csv', args, 'bpp_traits.csv');

export const downloadEnvironmentCsv = (args) => download('/export/environment.csv', args, 'bpp_environment.csv');

// The record of how `traits.csv` was sampled — recipe, per-row selection hits,
// DAS values actually used, frame counts, pipeline versions — saved as its own
// file because none of it can be recovered from the CSV's numbers afterwards.
// `provenance` is the user-facing word for it; `manifest` stays the API/code
// word, so the button and the endpoint deliberately do not share a name.
// Traits only: the environment manifest's row count is preview-only
// (`manifest_row_count_is_preview_only`) and would be a false number in a file
// that is meant to be citable.
export const downloadProvenanceJson = async (args) => {
  const r = await api.get(`/export/traits/manifest?${buildParams(args).toString()}`);
  const name = 'bpp_provenance.json';
  saveBlob(new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' }), name);
  // No `rows`: the confirmation renders it as "N rows" and this file is one
  // object describing an export, not N rows of data.
  return { filename: name, recipe: r.data?.recipe?.description };
};

// A failed export must say why (a 404 "no QC-correct observations in this window"
// is a real answer, not a bug) — the detail string is written for the user.
export const exportErrorMessage = (err) => {
  const d = err?.response?.data;
  if (typeof d === 'string' && d) return d;
  if (d?.detail) return typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
  return err?.message || 'Export failed.';
};
