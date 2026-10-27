/**
 * Admin batch-creation service (lean scope: create new batch only).
 *
 * All calls go through apiV2; there is no login.
 * Backend: /api/v2/admin/* + reused /api/v2/query/* read endpoints.
 */
import { apiV2 } from './api';

// Dropdown sources for the create form.
export const getBatchFormOptions = async () => {
  const res = await apiV2.get('/admin/batches/form-options');
  return res.data;
};

// Dry-run: expand the request into what would be written, without persisting.
export const previewBatch = async (payload) => {
  const res = await apiV2.post('/admin/batches/preview', payload);
  return res.data;
};

// Create the batch (and its plants + chamber history).
export const createBatch = async (payload) => {
  const res = await apiV2.post('/admin/batches', payload);
  return res.data;
};

// Dry-run: expand the plants that would be appended to an existing batch.
export const previewAppendPlants = async (batchCode, payload) => {
  const res = await apiV2.post(`/admin/batches/${encodeURIComponent(batchCode)}/plants/preview`, payload);
  return res.data;
};

// Append plants to an existing batch (incremental entry).
export const appendPlants = async (batchCode, payload) => {
  const res = await apiV2.post(`/admin/batches/${encodeURIComponent(batchCode)}/plants`, payload);
  return res.data;
};

// Existing observation plants of a batch with placement (for the edit table).
export const getObservationPlants = async (batchCode) => {
  const res = await apiV2.get(`/admin/batches/${encodeURIComponent(batchCode)}/observation-plants`);
  return res.data;
};

// A batch's existing shared defaults, to pre-fill the edit/append form.
export const getBatchDefaults = async (batchCode) => {
  const res = await apiV2.get(`/admin/batches/${encodeURIComponent(batchCode)}/defaults`);
  return res.data;
};

// Update placement/replicate of existing plants (typo fixes).
export const updatePlacements = async (batchCode, payload) => {
  const res = await apiV2.patch(`/admin/batches/${encodeURIComponent(batchCode)}/plants`, payload);
  return res.data;
};

// Map of raspi camera code (e.g. A1-102) -> rack_code (e.g. A1_1). Lets the
// coordinate page show which rack a loaded frame resolves to.
export const getCameraRackMap = async () => {
  const res = await apiV2.get('/admin/racks/camera-map');
  return res.data;
};

// Fetch a recorded reference frame image (from the local 8T1 archive via backend)
// as a Blob, so the coordinate page can auto-display it. Only works on the dev
// machine where the archive is mounted.
export const getReferenceFrame = async (filename) => {
  const res = await apiV2.get(`/admin/frames/${encodeURIComponent(filename)}`, { responseType: 'blob' });
  return res.data;
};

// Per-cultivar data completeness (raspi / 3D / thermal) + lifecycle gates.
export const getBatchDataStatus = async (batchCode) => {
  const res = await apiV2.get(`/admin/batches/${encodeURIComponent(batchCode)}/data-status`);
  return res.data;
};

// Toggle an event-backed milestone (e.g. digital_camera) for a cultivar.
export const setMilestone = async (batchCode, payload) => {
  const res = await apiV2.post(`/admin/batches/${encodeURIComponent(batchCode)}/milestone`, payload);
  return res.data;
};

// Minimal cultivar create (only cultivar_code required).
export const createCultivar = async (payload) => {
  const res = await apiV2.post('/admin/cultivars', payload);
  return res.data;
};

// Reused: full lightweight cultivar list (id, code, product_name) for table dropdowns.
export const getAllCultivars = async () => {
  const res = await apiV2.get('/query/cultivars/all');
  return res.data?.data ?? [];
};

// Reused: cultivar autocomplete search.
export const searchCultivars = async (searchTerm, limit = 20) => {
  const res = await apiV2.post('/query/cultivars/search', {
    search_term: searchTerm,
    limit,
    offset: 0,
  });
  return res.data;
};

// Reused: list existing batches for the admin list page.
export const listBatches = async () => {
  const res = await apiV2.get('/query/batches/with-cultivars');
  return res.data?.batches ?? [];
};
