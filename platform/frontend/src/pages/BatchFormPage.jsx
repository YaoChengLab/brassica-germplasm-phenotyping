import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Container, Form, Row, Col, Button, Spinner, Alert, Card } from 'react-bootstrap';
import PlantTableEditor, { blankRow } from '../components/admin/PlantTableEditor';
import PreviewModal from '../components/admin/PreviewModal';
import {
  getBatchFormOptions, getAllCultivars, createCultivar, previewBatch, createBatch,
} from '../services/adminBatchServiceV2';
import { buildPlantGroups, clean, missingDefaultDates } from '../components/admin/buildPlantGroups';
import { formatApiError as formatErr } from '../services/formatApiError';

const makeDefaults = (opts) => ({
  treatment_code: opts.treatments[0]?.treatment_code ?? 'Control',
  walkin_chamber_code: opts.walkinChambers[0] ?? 'R141',
  walkin_entry_date: '', walkin_exit_date: '',
  walkin_gc_id: opts.defaultWalkinGc ?? opts.growthConditions[0]?.id,
  obs_entry_date: '', obs_entry_time: '', obs_exit_date: '', obs_exit_time: '',
  obs_gc_id: opts.defaultObsGc ?? opts.growthConditions[0]?.id,
});

// --- Local draft autosave (survives refresh / browser / machine crash; per-browser) ---
const DRAFT_KEY = 'bpp_batch_draft_v1';
const draftHasContent = (s) =>
  !!(s && (String(s.batchCode || '').trim() ||
    (s.rows || []).some((r) => Object.values(r).some((v) => String(v ?? '').trim() !== ''))));
const loadDraft = () => {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    return draftHasContent(d) ? d : null;
  } catch { return null; }
};
const saveDraft = (s) => { try { localStorage.setItem(DRAFT_KEY, JSON.stringify(s)); } catch { /* quota/private mode */ } };
const clearDraft = () => { try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ } };

const BatchFormPage = () => {
  const navigate = useNavigate();
  const [options, setOptions] = useState(null);
  const [cultivars, setCultivars] = useState([]);
  const [loadErr, setLoadErr] = useState(null);

  const [batchCode, setBatchCode] = useState('');
  const [notes, setNotes] = useState('');
  const [defaults, setDefaults] = useState(null);
  const [rows, setRows] = useState([blankRow()]);

  // Draft state: hold any saved draft until the user chooses restore/discard,
  // and only autosave once that's resolved (so we never clobber it with the
  // empty initial form).
  const [draftResolved, setDraftResolved] = useState(false);
  const [pendingDraft, setPendingDraft] = useState(null);
  const [draftSavedAt, setDraftSavedAt] = useState(null);

  const [showPreview, setShowPreview] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const fo = await getBatchFormOptions();
        const opts = {
          treatments: fo.treatments,
          walkinChambers: fo.walkin_chamber_codes,
          growthConditions: fo.growth_conditions,
          g120Racks: fo.g120_racks,
          defaultWalkinGc: fo.default_walkin_growth_condition_id,
          defaultObsGc: fo.default_observation_growth_condition_id,
        };
        setOptions(opts);
        setDefaults(makeDefaults(opts));
        const saved = loadDraft();
        if (saved) setPendingDraft(saved); else setDraftResolved(true);
        try { setCultivars(await getAllCultivars()); } catch { /* dropdown stays empty; the code can still be typed in */ }
      } catch (e) {
        setLoadErr(e.response?.data?.detail || 'Failed to load form options (admin required)');
      }
    })();
  }, []);

  // Autosave once the draft decision is made (and form is initialised).
  useEffect(() => {
    if (!draftResolved || !defaults) return;
    const snap = { batchCode, notes, defaults, rows };
    if (!draftHasContent(snap)) return;
    saveDraft({ ...snap, savedAt: new Date().toISOString() });
    setDraftSavedAt(new Date());
  }, [batchCode, notes, defaults, rows, draftResolved]);

  const restoreDraft = () => {
    const d = pendingDraft;
    setBatchCode(d.batchCode || '');
    setNotes(d.notes || '');
    if (d.defaults) setDefaults(d.defaults);
    if (Array.isArray(d.rows) && d.rows.length) setRows(d.rows);
    setPendingDraft(null);
    setDraftResolved(true);
  };
  const discardDraft = () => { clearDraft(); setPendingDraft(null); setDraftResolved(true); };

  const addCultivar = async (code) => {
    try {
      const c = await createCultivar({ cultivar_code: code });
      setCultivars((prev) => (prev.some((x) => x.cultivar_code === c.cultivar_code) ? prev : [...prev, c]));
    } catch (e) {
      if (e.response?.status === 409) {
        setCultivars((prev) => (prev.some((x) => x.cultivar_code === code) ? prev : [...prev, { cultivar_code: code }]));
      } else {
        alert(e.response?.data?.detail || 'Failed to add cultivar');
      }
    }
  };

  const buildPayload = () => ({
    batch_code: batchCode.trim(),
    ...clean({ notes: notes.trim() }),
    plant_groups: buildPlantGroups(defaults, rows, false),
  });

  const openPreview = async () => {
    setShowPreview(true);
    setPreview(null);
    setPreviewErr(null);
    setPreviewLoading(true);
    try {
      setPreview(await previewBatch(buildPayload()));
    } catch (e) {
      setPreviewErr(formatErr(e));
    } finally {
      setPreviewLoading(false);
    }
  };

  const confirmCreate = async () => {
    setCreating(true);
    setPreviewErr(null);
    try {
      const res = await createBatch(buildPayload());
      clearDraft();
      const g = res.nursery_group_count;
      alert(`Created batch ${res.batch_code}: ${res.plant_count} plants (+${g} nursery group${g === 1 ? '' : 's'})`);
      navigate('/admin/batches');
    } catch (e) {
      setPreviewErr(formatErr(e));
    } finally {
      setCreating(false);
    }
  };

  if (loadErr) return <Container className="py-4"><Alert variant="danger">{loadErr}</Alert></Container>;
  if (!options || !defaults) return <Container className="py-5 text-center"><Spinner animation="border" /></Container>;

  const emptyCultivarRows = rows.filter((r) => !r.cultivar_code.trim()).length;
  const missingDates = missingDefaultDates(defaults);
  const canSubmit = batchCode.trim() && rows.length > 0 && emptyCultivarRows === 0 && missingDates.length === 0;

  return (
    <Container fluid className="py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="mb-0">New batch</h3>
        <Button variant="outline-secondary" onClick={() => navigate('/admin/batches')}>Back to list</Button>
      </div>

      {pendingDraft && (
        <Alert variant="warning" className="d-flex justify-content-between align-items-center">
          <span>
            Unsaved draft found ({pendingDraft.batchCode ? pendingDraft.batchCode : 'untitled'},
            {' '}{(pendingDraft.rows || []).length} rows
            {pendingDraft.savedAt ? `, saved ${new Date(pendingDraft.savedAt).toLocaleString()}` : ''})
            — restore?
          </span>
          <span className="d-flex gap-2">
            <Button size="sm" variant="warning" onClick={restoreDraft}>Restore</Button>
            <Button size="sm" variant="outline-secondary" onClick={discardDraft}>Discard</Button>
          </span>
        </Alert>
      )}

      <Card className="mb-3">
        <Card.Body>
          <Row className="g-3">
            <Col xs={12} md={4}>
              <Form.Label className="small fw-bold">Batch code</Form.Label>
              <Form.Control size="sm" placeholder="e.g. 2025B07" value={batchCode}
                onChange={(e) => setBatchCode(e.target.value)} />
              <Form.Text muted>Format YYYYBNN (4-digit year + B + 2-digit serial)</Form.Text>
            </Col>
            <Col xs={12} md={8}>
              <Form.Label className="small fw-bold">Notes (optional)</Form.Label>
              <Form.Control size="sm" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <PlantTableEditor
        defaults={defaults}
        onDefaults={setDefaults}
        rows={rows}
        onRows={setRows}
        options={options}
        cultivars={cultivars}
        onAddCultivar={addCultivar}
        showPlacement={false}
      />

      <div className="d-flex justify-content-end align-items-center gap-3">
        {draftSavedAt && (
          <span className="text-muted small">✓ Draft saved {draftSavedAt.toLocaleTimeString()}</span>
        )}
        {emptyCultivarRows > 0 && (
          <span className="text-danger small">{emptyCultivarRows} rows missing cultivar</span>
        )}
        {missingDates.length > 0 && (
          <span className="text-danger small">Missing defaults: {missingDates.join(', ')}</span>
        )}
        <Button variant="success" size="lg" onClick={openPreview} disabled={!canSubmit}>
          Preview &amp; create
        </Button>
      </div>

      <PreviewModal
        show={showPreview}
        preview={preview}
        loading={previewLoading}
        error={previewErr}
        creating={creating}
        onConfirm={confirmCreate}
        onClose={() => setShowPreview(false)}
      />
    </Container>
  );
};

export default BatchFormPage;
