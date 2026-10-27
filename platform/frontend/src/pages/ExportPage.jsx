// Structured export — where the platform hands off to downstream analysis.
//
// The platform's job ends at "get traceable data out": growth-model fitting,
// batch-effect correction and statistical testing live in the downstream analysis
// scripts. What this page must do, and does, is make the *sampling recipe*
// explicit and show it with the numbers — which days, which frame of each day,
// how far merged, which QC states — because none of that is recoverable from a
// column of values afterwards.
//
// Three columns: which plants, which traits, which window/recipe. Then a preview
// of the first rows (traits and environment are separate files, same business
// key) and the two downloads.
import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert, Badge, Button, Card, Col, Container, Form, Nav, Row, Spinner, Table,
} from 'react-bootstrap';
import { useQuery } from '@tanstack/react-query';
import Combobox from '../components/Combobox';
import { useComparison } from '../contexts/ComparisonContext';
import { fetchBatchesWithCultivars, fetchPlantsFor } from '../services/plantViewService';
import {
  downloadEnvironmentCsv, downloadProvenanceJson, downloadTraitsCsv, exportErrorMessage,
  fetchEnvironmentPreview, fetchExportOptions, fetchTraitPreview,
} from '../services/exportService';

const ANY = '';   // an empty business-key component means "every one of them"

// Same shape the backend reports back in `scope_hits` (`Scope.as_str`), so the
// per-row hit counts can be looked up by key without a second convention.
const scopeKey = (s) => [
  s.batch_code || '', s.cultivar_code || '', s.treatment_code || '', s.replicate_code ?? '',
].join('/');

const scopeLabel = (s) => [
  s.batch_code || 'any batch',
  s.cultivar_code || 'any cultivar',
  s.treatment_code || 'any treatment',
  s.replicate_code === '' || s.replicate_code == null ? 'all replicates' : `rep ${s.replicate_code}`,
].join(' / ');

const cardHead = { fontSize: '1rem', fontWeight: 600, marginBottom: 8 };
const smallMuted = { fontSize: '0.85rem', color: '#6c757d' };

const fmtCell = (v) => {
  if (v == null) return '';
  if (typeof v === 'number') return Number.isInteger(v) ? v : Number(v.toFixed(4));
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  return String(v);
};

const ExportPage = () => {
  const { comparisonItems, analysisWindow, setAnalysisWindow } = useComparison();

  const optionsQ = useQuery({ queryKey: ['export-options'], queryFn: fetchExportOptions, staleTime: Infinity });
  const opts = optionsQ.data;

  // ---------------------------------------------------------------- plants
  const [scopes, setScopes] = useState([]);
  const [batch, setBatch] = useState('');
  const [cultivar, setCultivar] = useState('');
  const [treatment, setTreatment] = useState(ANY);
  const [replicate, setReplicate] = useState(ANY);

  const batchesQ = useQuery({ queryKey: ['pv-batches'], queryFn: fetchBatchesWithCultivars });
  const batches = batchesQ.data || [];
  const cultivars = useMemo(
    () => batches.find((b) => b.batch_code === batch)?.cultivars || [],
    [batches, batch],
  );
  const plantsQ = useQuery({
    queryKey: ['pv-plants', batch, cultivar],
    queryFn: () => fetchPlantsFor(batch, cultivar),
    enabled: !!batch && !!cultivar,
  });
  const plants = plantsQ.data || [];
  const treatments = useMemo(() => [...new Set(plants.map((p) => p.treatment_code))].sort(), [plants]);
  const replicates = useMemo(
    () => plants
      .filter((p) => !treatment || p.treatment_code === treatment)
      .map((p) => p.replicate_code)
      .sort((a, b) => Number(a) - Number(b)),
    [plants, treatment],
  );

  const addScope = () => {
    if (!batch && !cultivar) return;
    const s = {
      batch_code: batch, cultivar_code: cultivar, treatment_code: treatment, replicate_code: replicate,
    };
    setScopes((prev) => (prev.some((p) => scopeKey(p) === scopeKey(s)) ? prev : [...prev, s]));
  };
  const removeScope = (key) => setScopes((prev) => prev.filter((s) => scopeKey(s) !== key));

  // The selection carried over from the Cultivar/Plant pages. Items added from the
  // Plant Viewer carry the full business key; items added from search results name
  // a cultivar only, which here means every replicate of it.
  const importSelection = () => {
    setScopes((prev) => {
      const next = [...prev];
      comparisonItems.forEach((i) => {
        const s = {
          batch_code: i.batch_code || ANY,
          cultivar_code: i.cultivar_code || ANY,
          treatment_code: i.treatment_code || ANY,
          replicate_code: i.replicate_code == null ? ANY : String(i.replicate_code),
        };
        if (!next.some((p) => scopeKey(p) === scopeKey(s))) next.push(s);
      });
      return next;
    });
  };

  // ---------------------------------------------------------------- traits
  const [traits, setTraits] = useState([]);
  const [traitFilter, setTraitFilter] = useState('');
  const [openCats, setOpenCats] = useState({});

  useEffect(() => {
    if (opts?.signature_traits && traits.length === 0) setTraits(opts.signature_traits);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts]);

  const toggleTrait = (t) => setTraits((prev) => (
    prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
  ));
  const setCategory = (cols, on) => setTraits((prev) => (
    on ? [...new Set([...prev, ...cols])] : prev.filter((t) => !cols.includes(t))
  ));

  const deprecated = opts?.deprecated_traits || {};
  const aliases = opts?.trait_aliases || {};
  const matches = (t) => !traitFilter || t.toLowerCase().includes(traitFilter.trim().toLowerCase());

  // ---------------------------------------------------------------- recipe
  const [recipe, setRecipe] = useState({
    preset: 'default',
    level: 'plant',
    day_mode: 'tail',
    n_days: 4,
    das_list: '',
    das_from: '',
    das_to: '',
    date_from: '',
    date_to: '',
    frame_pick: 'nearest_hour',
    pick_hour: 14,
    qc_status: ['auto', 'verified'],
    require_leaves: true,
    include_gdd: true,
    gdd_anchor: 'G120',
  });
  const [resolution, setResolution] = useState('day');
  const set = (k, v) => setRecipe((r) => ({ ...r, [k]: v }));

  // A DAS window picked on the Plant Viewer's curve arrives here as bounds and
  // becomes the day selection, once: after that the form owns it, so changing
  // day_mode by hand is not overwritten on every render.
  const [windowApplied, setWindowApplied] = useState(false);
  useEffect(() => {
    if (!analysisWindow || windowApplied) return;
    setRecipe((r) => ({
      ...r, day_mode: 'range', das_from: analysisWindow.das_min, das_to: analysisWindow.das_max,
    }));
    setWindowApplied(true);
  }, [analysisWindow, windowApplied]);

  // Picking a preset means "start from this recipe", so its resolved knobs are
  // copied into the form — the user can then see and change every one of them
  // rather than a preset name silently overriding what is displayed.
  const applyPreset = (name) => {
    const p = opts?.presets?.[name];
    if (!p) { set('preset', name); return; }
    setRecipe((r) => ({
      ...r,
      preset: name,
      level: p.level,
      day_mode: p.day_mode,
      n_days: p.n_days ?? r.n_days,
      das_list: (p.das_list || []).join(','),
      das_from: p.das_from ?? '',
      das_to: p.das_to ?? '',
      date_from: p.date_from ?? '',
      date_to: p.date_to ?? '',
      frame_pick: p.frame_pick,
      pick_hour: p.pick_hour,
      qc_status: p.qc_status,
      require_leaves: p.require_leaves,
      include_gdd: p.include_gdd,
      gdd_anchor: p.gdd_anchor,
    }));
  };
  const toggleQc = (v) => setRecipe((r) => ({
    ...r,
    qc_status: r.qc_status.includes(v) ? r.qc_status.filter((q) => q !== v) : [...r.qc_status, v],
  }));

  // ---------------------------------------------------------------- preview
  const [tab, setTab] = useState('traits');
  const [preview, setPreview] = useState(null);
  const [envPreview, setEnvPreview] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [lastDownload, setLastDownload] = useState(null);

  const args = { scopes, traits, recipe, resolution };
  const ready = scopes.length > 0 && traits.length > 0 && recipe.qc_status.length > 0;

  const runPreview = async (which) => {
    setError(''); setBusy(which);
    try {
      if (which === 'traits') setPreview(await fetchTraitPreview(args));
      else setEnvPreview(await fetchEnvironmentPreview({ ...args, resolution }));
      setTab(which);
    } catch (err) {
      setError(exportErrorMessage(err));
    } finally {
      setBusy('');
    }
  };

  const runDownload = async (which) => {
    setError(''); setBusy(`dl-${which}`);
    try {
      let info;
      if (which === 'traits') info = await downloadTraitsCsv(args);
      else if (which === 'environment') info = await downloadEnvironmentCsv({ ...args, resolution });
      else info = await downloadProvenanceJson(args);
      setLastDownload(info);
    } catch (err) {
      setError(exportErrorMessage(err));
    } finally {
      setBusy('');
    }
  };

  // A row that matches no plant should be flagged when it is added, not only after a
  // manual preview or a download, so the selection is previewed whenever it changes.
  useEffect(() => {
    if (ready) runPreview('traits');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopes]);

  if (optionsQ.isLoading) {
    return <Container className="py-4"><Spinner animation="border" /></Container>;
  }
  if (optionsQ.isError) {
    return (
      <Container className="py-4">
        <Alert variant="danger">
          Could not load the export options. {exportErrorMessage(optionsQ.error)}
        </Alert>
      </Container>
    );
  }

  const manifest = preview?.manifest;
  const envManifest = envPreview?.manifest;
  const shownPreview = tab === 'traits' ? preview : envPreview;

  // Per-row hit counts, keyed so they can be shown on the selection rows
  // themselves — that is where the row was picked and where a zero is a mistake
  // worth catching, not only in the summary at the bottom.
  const hitsByScope = {};
  (manifest?.scope_hits || []).forEach((h) => { hitsByScope[h.scope] = h; });
  const emptyScopes = manifest?.scopes_matching_nothing || [];

  return (
    <Container fluid className="py-4 px-4 large-font-page">
      <h3 className="mb-1">Export Data</h3>
      <p style={{ ...smallMuted, marginBottom: 16 }}>
        Structured CSV for downstream analysis. Growth-model parameters, batch-effect
        correction and statistical tests are not produced here — export the per-day
        series and fit them in the analysis scripts.
      </p>

      <Row className="g-3">
        {/* ------------------------------------------------------ plants */}
        <Col lg={4}>
          <Card body>
            <div style={cardHead}>1. Plants</div>
            <Form.Label className="mb-1 small">Batch</Form.Label>
            <Combobox
              options={batches.map((b) => ({ value: b.batch_code, label: b.batch_code }))}
              value={batch}
              onChange={(v) => { setBatch(v); setCultivar(''); setTreatment(ANY); setReplicate(ANY); }}
              placeholder="Batch…"
            />
            <Form.Label className="mb-1 mt-2 small">Cultivar</Form.Label>
            <Combobox
              options={cultivars.map((c) => ({
                value: c.cultivar_code,
                label: c.product_name ? `${c.cultivar_code} — ${c.product_name}` : c.cultivar_code,
              }))}
              value={cultivar}
              onChange={(v) => { setCultivar(v); setTreatment(ANY); setReplicate(ANY); }}
              disabled={!batch}
              placeholder={batch ? 'Cultivar…' : 'Pick a batch first'}
            />
            <Row className="g-2 mt-2">
              <Col xs={6}>
                <Form.Label className="mb-1 small">Treatment</Form.Label>
                <Form.Select
                  size="sm"
                  value={treatment}
                  onChange={(e) => { setTreatment(e.target.value); setReplicate(ANY); }}
                  disabled={!cultivar}
                >
                  <option value={ANY}>(all)</option>
                  {treatments.map((t) => <option key={t} value={t}>{t}</option>)}
                </Form.Select>
              </Col>
              <Col xs={6}>
                <Form.Label className="mb-1 small">Replicate</Form.Label>
                <Form.Select
                  size="sm"
                  value={replicate}
                  onChange={(e) => setReplicate(e.target.value)}
                  disabled={!cultivar}
                >
                  <option value={ANY}>(all)</option>
                  {replicates.map((r) => <option key={r} value={String(r)}>{r}</option>)}
                </Form.Select>
              </Col>
            </Row>
            <div className="d-flex gap-2 mt-3">
              <Button size="sm" onClick={addScope} disabled={!batch && !cultivar}>+ Add</Button>
              {comparisonItems.length > 0 && (
                <Button size="sm" variant="outline-secondary" onClick={importSelection}>
                  Add saved selection ({comparisonItems.length})
                </Button>
              )}
              {scopes.length > 0 && (
                <Button size="sm" variant="outline-secondary" onClick={() => setScopes([])}>Clear</Button>
              )}
            </div>

            <hr />
            <div style={smallMuted}>
              {scopes.length === 0
                ? 'Nothing selected yet. A row without a replicate covers every replicate.'
                : `${scopes.length} selection row${scopes.length === 1 ? '' : 's'} (combined with OR — `
                  + 'each row is matched on its own, so picking one cultivar per batch does not '
                  + 'pull in the other combinations).'}
            </div>
            {scopes.map((s) => {
              const hit = hitsByScope[scopeKey(s)];
              const dead = hit && hit.plants === 0;
              return (
                <div key={scopeKey(s)} className="mt-1">
                  <div className="d-flex justify-content-between align-items-center">
                    <code style={{ fontSize: '0.85rem' }}>{scopeLabel(s)}</code>
                    <span className="d-flex align-items-center gap-1">
                      {hit && (
                        <Badge bg={dead ? 'danger' : 'light'} text={dead ? 'light' : 'dark'}>
                          {hit.plants} plant{hit.plants === 1 ? '' : 's'}
                        </Badge>
                      )}
                      <Button variant="link" size="sm" className="py-0 text-danger"
                        onClick={() => removeScope(scopeKey(s))}>✕</Button>
                    </span>
                  </div>
                  {dead && (
                    <div style={{ fontSize: '0.8rem', color: '#b02a37' }}>{hit.reason}</div>
                  )}
                </div>
              );
            })}
            {scopes.length > 0 && !manifest && (
              <div style={{ ...smallMuted, marginTop: 6 }}>
                Preview to see how many plants each row actually matches.
              </div>
            )}
          </Card>
        </Col>

        {/* ------------------------------------------------------ traits */}
        <Col lg={4}>
          <Card body>
            <div style={cardHead}>
              2. Traits <Badge bg="secondary">{traits.length}</Badge>
            </div>
            <Form.Control
              size="sm"
              placeholder="Filter by name…"
              value={traitFilter}
              onChange={(e) => setTraitFilter(e.target.value)}
            />
            <div className="mt-2" style={{ maxHeight: 420, overflowY: 'auto' }}>
              <div className="fw-semibold small mt-1">Signature traits</div>
              {/* The signature traits also live in their own categories below, so the
                  checkbox ids are scoped — a duplicate id would make one label
                  toggle the other checkbox. */}
              {(opts.signature_traits || []).filter(matches).map((t) => (
                <Form.Check
                  key={t} type="checkbox" id={`sig-${t}`} label={t}
                  checked={traits.includes(t)} onChange={() => toggleTrait(t)}
                  style={{ fontSize: '0.9rem' }}
                />
              ))}

              {Object.entries(opts.trait_categories || {}).map(([cat, cols]) => {
                const shown = cols.filter(matches);
                if (!shown.length) return null;
                const open = openCats[cat] || !!traitFilter;
                const nSel = cols.filter((c) => traits.includes(c)).length;
                return (
                  <div key={cat} className="mt-2">
                    <div className="d-flex justify-content-between align-items-center">
                      <Button
                        variant="link" size="sm" className="px-0 text-decoration-none"
                        onClick={() => setOpenCats((o) => ({ ...o, [cat]: !open }))}
                      >
                        {open ? '▾' : '▸'} {cat}{' '}
                        <span style={smallMuted}>({nSel}/{cols.length})</span>
                      </Button>
                      {open && (
                        <span>
                          <Button variant="link" size="sm" className="py-0"
                            onClick={() => setCategory(shown, true)}>all</Button>
                          <Button variant="link" size="sm" className="py-0"
                            onClick={() => setCategory(shown, false)}>none</Button>
                        </span>
                      )}
                    </div>
                    {open && shown.map((t) => (
                      <Form.Check
                        key={t} type="checkbox" id={`cat-${cat}-${t}`}
                        checked={traits.includes(t)} onChange={() => toggleTrait(t)}
                        style={{ fontSize: '0.9rem' }}
                        label={
                          <span>
                            {t}
                            {deprecated[t] && (
                              <span style={smallMuted} title={deprecated[t]}> — deprecated</span>
                            )}
                            {aliases[t] && (
                              <span style={smallMuted} title={aliases[t].note}>
                                {' '}— same as {aliases[t].same_as}
                              </span>
                            )}
                          </span>
                        }
                      />
                    ))}
                  </div>
                );
              })}

              {/* Kept available but collapsed: that growth and shape-dynamics traits are
                  fitted downstream is a normal division of labour, not a caveat the page
                  needs to lead with. It stays reachable so nobody has to wonder why the
                  master table has more columns than this picker. */}
              <details className="mt-3">
                <summary className="fw-semibold small" style={{ cursor: 'pointer' }}>
                  Fitted downstream, not exportable ({(opts.downstream_only_traits || []).length})
                </summary>
                <div style={smallMuted}>{opts.downstream_only_note}</div>
                <div style={{ ...smallMuted, marginTop: 4 }}>
                  {(opts.downstream_only_traits || []).join(', ')}
                </div>
              </details>
            </div>
          </Card>
        </Col>

        {/* ------------------------------------------------- window/recipe */}
        <Col lg={4}>
          <Card body>
            <div style={cardHead}>3. Window &amp; sampling recipe</div>

            {analysisWindow && (
              <Alert variant="info" className="py-2 mb-2" style={{ fontSize: '0.85rem' }}>
                Window from the Plant Viewer: DAS {analysisWindow.das_min}–{analysisWindow.das_max}
                <Button variant="link" size="sm" className="py-0"
                  onClick={() => setAnalysisWindow(null)}>clear</Button>
              </Alert>
            )}
            <Form.Label className="mb-1 small">Start from preset</Form.Label>
            <Form.Select size="sm" value={recipe.preset} onChange={(e) => applyPreset(e.target.value)}>
              {Object.keys(opts.presets || {}).map((n) => <option key={n} value={n}>{n}</option>)}
            </Form.Select>
            <div style={{ ...smallMuted, marginTop: 4 }}>{opts.presets?.[recipe.preset]?.note}</div>

            <Row className="g-2 mt-2">
              <Col xs={7}>
                <Form.Label className="mb-1 small">Which days</Form.Label>
                <Form.Select size="sm" value={recipe.day_mode} onChange={(e) => set('day_mode', e.target.value)}>
                  {(opts.day_modes || []).map((m) => <option key={m} value={m}>{m}</option>)}
                </Form.Select>
              </Col>
              <Col xs={5}>
                {recipe.day_mode === 'tail' && (
                  <>
                    <Form.Label className="mb-1 small">Last n days</Form.Label>
                    <Form.Control size="sm" type="number" min={1} max={400} value={recipe.n_days}
                      onChange={(e) => set('n_days', e.target.value)} />
                  </>
                )}
              </Col>
            </Row>
            {recipe.day_mode === 'list' && (
              <>
                <Form.Label className="mb-1 mt-2 small">DAS values (comma-separated)</Form.Label>
                <Form.Control size="sm" value={recipe.das_list} placeholder="28,30,32,34"
                  onChange={(e) => set('das_list', e.target.value)} />
              </>
            )}
            {recipe.day_mode === 'range' && (
              <Row className="g-2 mt-2">
                <Col xs={6}>
                  <Form.Label className="mb-1 small">DAS from</Form.Label>
                  <Form.Control size="sm" type="number" value={recipe.das_from}
                    onChange={(e) => set('das_from', e.target.value)} />
                </Col>
                <Col xs={6}>
                  <Form.Label className="mb-1 small">DAS to</Form.Label>
                  <Form.Control size="sm" type="number" value={recipe.das_to}
                    onChange={(e) => set('das_to', e.target.value)} />
                </Col>
              </Row>
            )}
            {recipe.day_mode === 'dates' && (
              <Row className="g-2 mt-2">
                <Col xs={6}>
                  <Form.Label className="mb-1 small">Date from</Form.Label>
                  <Form.Control size="sm" type="date" value={recipe.date_from}
                    onChange={(e) => set('date_from', e.target.value)} />
                </Col>
                <Col xs={6}>
                  <Form.Label className="mb-1 small">Date to</Form.Label>
                  <Form.Control size="sm" type="date" value={recipe.date_to}
                    onChange={(e) => set('date_to', e.target.value)} />
                </Col>
              </Row>
            )}

            <Row className="g-2 mt-2">
              <Col xs={7}>
                <Form.Label className="mb-1 small">Image within a day</Form.Label>
                <Form.Select size="sm" value={recipe.frame_pick} onChange={(e) => set('frame_pick', e.target.value)}>
                  {(opts.frame_picks || []).map((m) => <option key={m} value={m}>{m}</option>)}
                </Form.Select>
              </Col>
              <Col xs={5}>
                {recipe.frame_pick === 'nearest_hour' && (
                  <>
                    <Form.Label className="mb-1 small">Target hour</Form.Label>
                    <Form.Control size="sm" type="number" min={0} max={24} step={0.5}
                      value={recipe.pick_hour} onChange={(e) => set('pick_hour', e.target.value)} />
                  </>
                )}
              </Col>
            </Row>

            <Form.Label className="mb-1 mt-2 small">Merge to</Form.Label>
            <Form.Select size="sm" value={recipe.level} onChange={(e) => set('level', e.target.value)}>
              {(opts.levels || []).map((l) => <option key={l} value={l}>{l === 'frame' ? 'single-plant image' : l}</option>)}
            </Form.Select>
            <div style={{ ...smallMuted, marginTop: 4 }}>
              single-plant image = one row per image · day = per plant-day · plant = one row per plant ·
              cultivar = mean ± SD across replicates
            </div>

            <div className="d-flex align-items-center gap-3 mt-2">
              <span className="small">QC</span>
              {(opts.qc_values || []).map((q) => (
                <Form.Check
                  key={q} inline type="checkbox" id={`qc-${q}`} label={q}
                  checked={recipe.qc_status.includes(q)} onChange={() => toggleQc(q)}
                  style={{ fontSize: '0.9rem' }}
                />
              ))}
            </div>
            {recipe.qc_status.includes('no') && (
              <div style={{ ...smallMuted, color: '#b02a37' }}>
                &lsquo;no&rsquo; rows are pre-QC (leaf ownership not applied). Included only because
                you asked; it is recorded in the manifest.
              </div>
            )}

            <Form.Check
              className="mt-2" type="checkbox" id="require-leaves" label="Skip single-plant images with no retained leaf"
              checked={recipe.require_leaves} onChange={(e) => set('require_leaves', e.target.checked)}
              style={{ fontSize: '0.9rem' }}
            />
            <Form.Check
              type="checkbox" id="include-gdd" label={`Attach thermal time (GDD, aligned on ${recipe.gdd_anchor} entry)`}
              checked={recipe.include_gdd} onChange={(e) => set('include_gdd', e.target.checked)}
              style={{ fontSize: '0.9rem' }}
            />
            {recipe.include_gdd && <div style={smallMuted}>{opts.gdd?.note}</div>}

            <hr />
            <Form.Label className="mb-1 small">Environment file resolution</Form.Label>
            <Form.Select size="sm" value={resolution} onChange={(e) => setResolution(e.target.value)}>
              {(opts.environment?.resolutions || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </Form.Select>
            <div style={{ ...smallMuted, marginTop: 4 }}>{opts.environment?.note}</div>
          </Card>
        </Col>
      </Row>

      {/* ------------------------------------------------------- preview */}
      <Card body className="mt-3">
        <div className="d-flex flex-wrap align-items-center gap-2">
          <Button size="sm" onClick={() => runPreview('traits')} disabled={!ready || !!busy}>
            {busy === 'traits' ? 'Loading…' : 'Preview traits'}
          </Button>
          <Button size="sm" variant="outline-primary" onClick={() => runPreview('environment')}
            disabled={!ready || !!busy}>
            {busy === 'environment' ? 'Loading…' : 'Preview environment'}
          </Button>
          <div className="ms-auto d-flex gap-2">
            <Button size="sm" variant="success" onClick={() => runDownload('traits')} disabled={!ready || !!busy}>
              {busy === 'dl-traits' ? 'Preparing…' : 'Download traits.csv'}
            </Button>
            <Button size="sm" variant="outline-success" onClick={() => runDownload('environment')}
              disabled={!ready || !!busy}>
              {busy === 'dl-environment' ? 'Preparing…' : 'Download environment.csv'}
            </Button>
            {/* The sampling recipe travels as its own citable file, not only as
                the on-screen summary — it describes the trait export. */}
            <Button size="sm" variant="outline-secondary" onClick={() => runDownload('provenance')}
              disabled={!ready || !!busy}
              title="How traits.csv was sampled: recipe, selection hits, DAS values used, image counts, pipeline versions.">
              {busy === 'dl-provenance' ? 'Preparing…' : 'Download provenance JSON'}
            </Button>
          </div>
        </div>
        {!ready && (
          <div style={{ ...smallMuted, marginTop: 8 }}>
            Add at least one selection row, one trait and one QC state.
          </div>
        )}
        {error && <Alert variant="danger" className="mt-2 mb-0">{error}</Alert>}
        {lastDownload && (
          <Alert
            variant={/MATCHED NOTHING/.test(lastDownload.scopes || '') ? 'warning' : 'success'}
            className="mt-2 mb-0"
            style={{ fontSize: '0.9rem' }}
          >
            Saved <code>{lastDownload.filename}</code>
            {lastDownload.rows ? ` — ${lastDownload.rows} rows` : ''}
            {lastDownload.recipe ? <div><strong>Recipe:</strong> {lastDownload.recipe}</div> : null}
            {lastDownload.gdd ? <div><strong>GDD:</strong> {lastDownload.gdd}</div> : null}
            {lastDownload.scopes ? <div><strong>Selection:</strong> {lastDownload.scopes}</div> : null}
          </Alert>
        )}

        {/* The recipe string travels with the numbers wherever they are shown: it
            cannot be reconstructed from the values, and a preview without it
            invites reading the wrong window into the figures. */}
        {(manifest || envManifest) && (
          <div className="mt-3" style={{ fontSize: '0.9rem' }}>
            <div>
              <strong>Sampling recipe:</strong>{' '}
              {manifest?.recipe?.description
                || `${envManifest?.window?.day_mode} window — ${envManifest?.window?.note}`}
            </div>
            {tab === 'traits' && manifest && (
              <div style={smallMuted}>
                {manifest.row_count.toLocaleString()} rows · {manifest.plant_count} plants ·
                {' '}DAS used {manifest.das_values_used?.join(', ') || '—'} ·
                {' '}{manifest.frames_used_total?.toLocaleString()} single-plant images
                {manifest.gdd?.included
                  ? ` · GDD ${manifest.gdd.plant_days_with_value}/${manifest.gdd.plant_days_total} plant-days`
                  : ''}
                {manifest.provenance?.pipeline_versions?.length
                  ? ` · pipeline ${manifest.provenance.pipeline_versions.join(', ')}`
                  : ''}
              </div>
            )}
            {tab === 'traits' && manifest?.gdd?.included && !manifest.gdd.plant_days_with_value && (
              <Alert variant="warning" className="mt-2 mb-0 py-2" style={{ fontSize: '0.9rem' }}>
                Every GDD cell in this selection is empty: there are no environment records for
                these chamber-days. Empty must not be read as 0.
              </Alert>
            )}
            {/* An empty environment result must explain itself; an empty table would
                read as "no conditions recorded ≈ nothing happened". */}
            {tab === 'environment' && envPreview?.empty_reason && (
              <Alert variant="warning" className="mt-2 mb-0 py-2" style={{ fontSize: '0.9rem' }}>
                {envPreview.empty_reason}
              </Alert>
            )}
            {tab === 'environment' && envManifest && (
              <div style={smallMuted}>
                resolution {envManifest.level} · {envManifest.columns?.length} columns ·
                {' '}chamber-level series ({envManifest.method?.resolution}) ·
                {' '}filter on n_hours_observed
              </div>
            )}
            {preview?.too_large && (
              <Alert variant="warning" className="mt-2 mb-0 py-2" style={{ fontSize: '0.9rem' }}>
                {manifest.row_count.toLocaleString()} rows exceeds the {opts.max_rows.toLocaleString()}
                {' '}download limit. Narrow the selection or merge to day/plant.
              </Alert>
            )}
          </div>
        )}

        {/* What the selection actually caught. Totals alone hide a row that
            matched nothing — the row contributes 0 and the total still looks
            plausible, which is the quiet under-selection twin of the flat
            filters' quiet cross product. */}
        {tab === 'traits' && manifest?.scope_hits?.length > 0 && (
          <div className="mt-3">
            {emptyScopes.length > 0 && (
              <Alert variant="danger" className="py-2 mb-2" style={{ fontSize: '0.9rem' }}>
                {emptyScopes.length} selection row{emptyScopes.length === 1 ? '' : 's'} matched no
                plants, so this export covers less than was picked:{' '}
                <code>{emptyScopes.join('  ')}</code>
              </Alert>
            )}
            <div style={cardHead}>Selection coverage</div>
            <Table bordered hover size="sm" style={{ fontSize: '0.82rem', marginBottom: 8 }}>
              <thead>
                <tr>
                  <th>Selection row</th>
                  <th className="text-end">Plants in file</th>
                  <th className="text-end">Plants existing</th>
                  <th className="text-end">Images</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {manifest.scope_hits.map((h) => (
                  <tr key={h.scope} className={h.plants ? '' : 'table-danger'}>
                    <td><code>{h.scope}</code></td>
                    <td className="text-end">{h.plants}</td>
                    <td className="text-end">{h.plants_existing}</td>
                    <td className="text-end">{h.frames.toLocaleString()}</td>
                    <td>{h.reason || ''}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div style={{ ...smallMuted, marginBottom: 8 }}>
              {manifest.plant_count} distinct plant{manifest.plant_count === 1 ? '' : 's'} in the file
              {manifest.scope_hits_overlap
                ? ' — the row counts add up to more than that because rows overlap '
                  + '(a cultivar row and one of its replicates count the same plant twice).'
                : '.'}
              {' '}“Plants existing” ignores the window and the QC states, so a row with plants
              existing but 0 in the file is a real gap in the data, not a typo in the picks.
            </div>
            <div style={{ maxHeight: 280, overflowY: 'auto' }}>
              <Table striped bordered size="sm" style={{ fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
                <thead>
                  <tr>
                    <th>Plant (business key)</th>
                    <th>plant_id</th>
                    <th className="text-end">Days</th>
                    <th className="text-end">Images</th>
                    <th>DAS used</th>
                    <th>QC</th>
                  </tr>
                </thead>
                <tbody>
                  {(manifest.coverage || []).map((c) => (
                    <tr key={c.plant_id}>
                      <td>
                        <code>
                          {[c.batch_code, c.cultivar_code, c.treatment_code || '—', c.replicate_code].join('_')}
                        </code>
                      </td>
                      <td>{c.plant_id}</td>
                      <td className="text-end">{c.n_days_used}</td>
                      <td className="text-end">{c.n_frames_used}</td>
                      <td>{c.das_used}</td>
                      <td>{c.all_verified ? 'verified' : 'mixed / auto'}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
            {manifest.coverage_truncated && (
              <div style={smallMuted}>
                Only the first {manifest.coverage?.length} plants are listed here; the full list is
                in the manifest.
              </div>
            )}
          </div>
        )}

        {(preview || envPreview) && (
          <>
            <Nav variant="tabs" activeKey={tab} onSelect={(k) => setTab(k)} className="mt-3">
              <Nav.Item><Nav.Link eventKey="traits" disabled={!preview}>Traits</Nav.Link></Nav.Item>
              <Nav.Item><Nav.Link eventKey="environment" disabled={!envPreview}>Environment</Nav.Link></Nav.Item>
            </Nav>
            {shownPreview && (
              <div style={{ overflowX: 'auto', maxHeight: 420 }}>
                <Table striped bordered hover size="sm" style={{ fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
                  <thead>
                    <tr>{shownPreview.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {shownPreview.rows.map((row, i) => (
                      // eslint-disable-next-line react/no-array-index-key
                      <tr key={i}>
                        {shownPreview.columns.map((c) => <td key={c}>{fmtCell(row[c])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </Table>
                <div style={smallMuted}>
                  {shownPreview.preview_rows === 0
                    ? 'No rows for this selection.'
                    : `First ${shownPreview.preview_rows} row(s) only. The full file is the download.`}
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      <div className="mt-3" style={smallMuted}>
        Values are pixel-based (single top-view camera, no in-plane scale reference at leaf
        height) — not converted to physical units. Traits and environment are two files with
        the same business key; join on batch / cultivar / treatment / replicate (+ date or DAS).
      </div>
    </Container>
  );
};

export default ExportPage;
