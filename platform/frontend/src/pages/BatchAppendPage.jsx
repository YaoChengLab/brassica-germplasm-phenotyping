import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Container, Button, Spinner, Alert } from 'react-bootstrap';
import PlantTableEditor from '../components/admin/PlantTableEditor';
import PreviewModal from '../components/admin/PreviewModal';
import {
  getBatchFormOptions, getAllCultivars, createCultivar,
  getObservationPlants, updatePlacements, previewAppendPlants, appendPlants, getBatchDefaults,
} from '../services/adminBatchServiceV2';
import { buildPlantGroups, missingDefaultDates } from '../components/admin/buildPlantGroups';
import { formatApiError as formatErr } from '../services/formatApiError';

// Pre-fill from the batch's existing record (bd), falling back to option defaults
// when a field isn't recorded. bd null => plain option defaults.
const makeDefaults = (opts, bd = null) => ({
  treatment_code: bd?.treatment_code ?? opts.treatments[0]?.treatment_code ?? 'Control',
  walkin_chamber_code: bd?.walkin_chamber_code ?? opts.walkinChambers[0] ?? 'R141',
  walkin_entry_date: bd?.walkin_entry_date ?? '',
  walkin_exit_date: bd?.walkin_exit_date ?? '',
  walkin_gc_id: bd?.walkin_gc_id ?? opts.defaultWalkinGc ?? opts.growthConditions[0]?.id,
  obs_entry_date: bd?.obs_entry_date ?? '',
  obs_entry_time: bd?.obs_entry_time ?? '',
  obs_exit_date: bd?.obs_exit_date ?? '',
  obs_exit_time: bd?.obs_exit_time ?? '',
  obs_gc_id: bd?.obs_gc_id ?? opts.defaultObsGc ?? opts.growthConditions[0]?.id,
});

// Map a fetched observation plant to a locked existing table row.
const toExistingRow = (p) => ({
  _existing: true,
  plant_id: p.plant_id,
  cultivar_code: p.cultivar_code ?? '',
  replicate_code: p.replicate_code ?? '',
  rack_code: p.rack_code ?? '',
  coordinate_x: p.coordinate_x ?? '',
  coordinate_y: p.coordinate_y ?? '',
});

const placementKey = (r) =>
  `${r.replicate_code}|${r.rack_code}|${r.coordinate_x}|${r.coordinate_y}`;

const draftHasContent = (s) =>
  !!(s && (s.rows || []).some((r) => Object.values(r).some((v) => String(v ?? '').trim() !== '')));

// Genuine unsaved work: a changed existing row, or a new row with a cultivar.
// Merely loading existing plants is NOT work — otherwise a draft would be
// auto-created (and the banner would reappear) for every batch on every visit.
const rowsHaveEdits = (rows, orig) => (rows || []).some((r) => (r._existing
  ? orig[r.plant_id] !== placementKey(r)
  : String(r.cultivar_code ?? '').trim() !== ''));

const BatchAppendPage = () => {
  const navigate = useNavigate();
  const { batchCode } = useParams();
  const DRAFT_KEY = `bpp_batch_edit_draft_v1:${batchCode}`;
  const loadDraft = () => {
    try { const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); return draftHasContent(d) ? d : null; }
    catch { return null; }
  };
  const saveDraft = (s) => { try { localStorage.setItem(DRAFT_KEY, JSON.stringify(s)); } catch { /* ignore */ } };
  const clearDraft = () => { try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ } };

  const [options, setOptions] = useState(null);
  const [cultivars, setCultivars] = useState([]);
  const [loadErr, setLoadErr] = useState(null);

  const [defaults, setDefaults] = useState(null);
  const [rows, setRows] = useState([]);
  // Original placement of each existing plant, to detect typo fixes on save.
  const [original, setOriginal] = useState({});

  const [draftResolved, setDraftResolved] = useState(false);
  const [pendingDraft, setPendingDraft] = useState(null);
  const [draftSavedAt, setDraftSavedAt] = useState(null);

  const [showPreview, setShowPreview] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState(null);
  const [saving, setSaving] = useState(false);

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
        let bd = null;
        try { bd = await getBatchDefaults(batchCode); } catch { /* fall back to option defaults */ }
        setDefaults(makeDefaults(opts, bd));

        const existing = (await getObservationPlants(batchCode)).map(toExistingRow);
        const origMap = Object.fromEntries(existing.map((r) => [r.plant_id, placementKey(r)]));
        setOriginal(origMap);

        const saved = loadDraft();
        if (saved && rowsHaveEdits(saved.rows, origMap)) {
          setPendingDraft(saved);
        } else {
          if (saved) clearDraft(); // stale draft with no real edits -> drop silently
          setRows([...existing]); // no default blank row — append via the "+ Add row" button
          setDraftResolved(true);
        }
        try { setCultivars(await getAllCultivars()); } catch { /* the code can still be typed in */ }
      } catch (e) {
        setLoadErr(e.response?.data?.detail || 'Failed to load (admin required or batch not found)');
      }
    })();
  }, [batchCode]);

  useEffect(() => {
    if (!draftResolved || !defaults) return;
    // Persist only genuine unsaved work; otherwise clear any draft so an untouched
    // or just-discarded page doesn't re-create one.
    if (rowsHaveEdits(rows, original)) {
      saveDraft({ defaults, rows, savedAt: new Date().toISOString() });
      setDraftSavedAt(new Date());
    } else {
      clearDraft();
      setDraftSavedAt(null);
    }
  }, [defaults, rows, original, draftResolved]);

  const restoreDraft = () => {
    const d = pendingDraft;
    if (d.defaults) setDefaults(d.defaults);
    if (Array.isArray(d.rows)) setRows(d.rows);
    setPendingDraft(null);
    setDraftResolved(true);
  };
  const discardDraft = async () => {
    clearDraft();
    // discard reverts to freshly-loaded existing rows + a blank new row
    const existing = (await getObservationPlants(batchCode)).map(toExistingRow);
    setOriginal(Object.fromEntries(existing.map((r) => [r.plant_id, placementKey(r)])));
    setRows([...existing]); // no default blank row — append via the "+ Add row" button
    setPendingDraft(null);
    setDraftResolved(true);
  };

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

  // What will be sent: changed existing rows -> PATCH; filled new rows -> append.
  const changedUpdates = () =>
    rows.filter((r) => r._existing && original[r.plant_id] !== placementKey(r))
      .map((r) => ({
        plant_id: r.plant_id,
        replicate_code: Number(r.replicate_code),
        rack_code: r.rack_code,
        coordinate_x: Number(r.coordinate_x),
        coordinate_y: Number(r.coordinate_y),
      }));
  const newRows = () => rows.filter((r) => !r._existing && r.cultivar_code.trim());

  const saveAll = async () => {
    setSaving(true);
    setPreviewErr(null);
    try {
      const updates = changedUpdates();
      const groups = buildPlantGroups(defaults, newRows());
      let msg = [];
      if (updates.length) {
        const u = await updatePlacements(batchCode, { updates });
        msg.push(`updated ${u.updated_count} plants`);
      }
      if (groups.length) {
        const a = await appendPlants(batchCode, { plant_groups: groups });
        const ngLabel = (n) => `${n} nursery group${n === 1 ? '' : 's'}`;
        msg.push(`added ${a.added_plant_count} plants (+${ngLabel(a.added_nursery_group_count)}), `
          + `batch now ${a.plant_count_total} plants (+${ngLabel(a.nursery_group_count_total)})`);
      }
      clearDraft();
      alert(`${batchCode} saved: ${msg.join('; ') || 'no changes'}`);
      navigate('/admin/batches');
    } catch (e) {
      setPreviewErr(formatErr(e));
      setShowPreview(true); // keep modal open to show error if it was open
    } finally {
      setSaving(false);
    }
  };

  const onSubmit = async () => {
    const groups = buildPlantGroups(defaults, newRows());
    if (groups.length) {
      // preview the additions, then confirm runs saveAll (which also patches edits)
      setShowPreview(true);
      setPreview(null);
      setPreviewErr(null);
      setPreviewLoading(true);
      try {
        setPreview(await previewAppendPlants(batchCode, { plant_groups: groups }));
      } catch (e) {
        setPreviewErr(formatErr(e));
      } finally {
        setPreviewLoading(false);
      }
    } else {
      // only edits, no additions — save directly
      await saveAll();
    }
  };

  if (loadErr) return <Container className="py-4"><Alert variant="danger">{loadErr}</Alert></Container>;
  if (!options || !defaults) return <Container className="py-5 text-center"><Spinner animation="border" /></Container>;

  const newWithoutCultivar = rows.filter(
    (r) => !r._existing && !r.cultivar_code.trim() &&
      [r.replicate_code, r.rack_code, r.coordinate_x, r.coordinate_y].some((v) => String(v).trim() !== '')
  ).length;
  const nUpdates = changedUpdates().length;
  const nNew = newRows().length;
  // Dates are only required when appending new plants (edits don't use them).
  const missingDates = nNew > 0 ? missingDefaultDates(defaults) : [];
  const canSubmit = (nUpdates > 0 || nNew > 0) && newWithoutCultivar === 0 && missingDates.length === 0;

  return (
    <Container fluid className="py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="mb-0">Edit / append plants: <span className="text-primary">{batchCode}</span></h3>
        <Button variant="outline-secondary" onClick={() => navigate('/admin/batches')}>Back to list</Button>
      </div>

      <Alert variant="info" className="py-2 mb-3">
        Existing plants (<strong>saved</strong>) have a locked cultivar and can&apos;t be deleted here,
        but rack / coords / rep can be fixed inline. New rows add new cultivars.
        <strong> Append is for new cultivars</strong>; adding more replicates of the same cultivar is handled separately.
      </Alert>

      {pendingDraft && (
        <Alert variant="warning" className="d-flex justify-content-between align-items-center">
          <span>
            Unsaved edit draft for {batchCode} ({(pendingDraft.rows || []).length} rows
            {pendingDraft.savedAt ? `, saved ${new Date(pendingDraft.savedAt).toLocaleString()}` : ''}) — restore?
          </span>
          <span className="d-flex gap-2">
            <Button size="sm" variant="warning" onClick={restoreDraft}>Restore</Button>
            <Button size="sm" variant="outline-secondary" onClick={discardDraft}>Discard</Button>
          </span>
        </Alert>
      )}

      <PlantTableEditor
        defaults={defaults}
        onDefaults={setDefaults}
        rows={rows}
        onRows={setRows}
        options={options}
        cultivars={cultivars}
        onAddCultivar={addCultivar}
      />

      <div className="d-flex justify-content-end align-items-center gap-3">
        {draftSavedAt && (
          <span className="text-muted small">✓ Draft saved {draftSavedAt.toLocaleTimeString()}</span>
        )}
        {newWithoutCultivar > 0 && (
          <span className="text-danger small">{newWithoutCultivar} rows have data but no cultivar</span>
        )}
        {missingDates.length > 0 && (
          <span className="text-danger small">Appending needs defaults: {missingDates.join(', ')}</span>
        )}
        <span className="text-muted small">Pending: {nUpdates} edits, {nNew} new</span>
        <Button variant="success" size="lg" onClick={onSubmit} disabled={!canSubmit || saving}>
          {saving ? 'Saving…' : 'Preview & save'}
        </Button>
      </div>

      <PreviewModal
        show={showPreview}
        preview={preview}
        loading={previewLoading}
        error={previewErr}
        creating={saving}
        onConfirm={saveAll}
        onClose={() => setShowPreview(false)}
      />
    </Container>
  );
};

export default BatchAppendPage;
