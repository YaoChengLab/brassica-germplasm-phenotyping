// Plant viewer service. Uses the single API client (apiV2 = api, /api/v1).
import { apiV2 as api } from './api';

const API_BASE = import.meta.env.VITE_APP_API_URL || '/api/v1';

// source of the batch -> accession dropdowns
export const fetchBatchesWithCultivars = async () => {
  const r = await api.get('/query/batches/with-cultivars');
  return r.data.batches || [];
};

// After a batch and accession are chosen, list their plants (treatment / replicate).
// Only observation_individual: a nursery_group is the seedling-tray parent record (no
// replicate, no images) and cannot be viewed.
export const fetchPlantsFor = async (batchCode, cultivarCode) => {
  const r = await api.get('/query/plants', {
    params: { batch_code: batchCode, cultivar_code: cultivarCode, limit: 200 },
  });
  return (r.data.data || []).filter((p) => p.plant_type === 'observation_individual');
};

// Expand one selection (an accession code alone or a full plant key) into its plants.
// Each item is queried on its own: sending them together would give the cross product
// (see the scopes of the export).
export const fetchPlantsForSelection = async (item) => {
  const params = { limit: 200 };
  if (item.batch_code) params.batch_code = item.batch_code;
  if (item.cultivar_code) params.cultivar_code = item.cultivar_code;
  if (item.treatment_code) params.treatment_code = item.treatment_code;
  if (item.replicate_code != null && item.replicate_code !== '') params.replicate_code = item.replicate_code;
  const r = await api.get('/query/plants', { params });
  return (r.data.data || []).filter((p) => p.plant_type === 'observation_individual');
};

// plant key (four fields) -> the one plant (with sowing date and DAS range)
export const resolvePlant = async ({ batchCode, cultivarCode, treatmentCode, replicateCode }) => {
  const r = await api.get('/plant-view/resolve', {
    params: {
      batch_code: batchCode, cultivar_code: cultivarCode,
      treatment_code: treatmentCode, replicate_code: replicateCode,
    },
  });
  return r.data;
};

// image-trait time series of one plant (without fields the back end returns its 6 default
// traits + qc_status). fields go as repeated `fields=` parameters (FastAPI's List[str]);
// axios would serialise them as `fields[]=`, which the back end ignores, so the query
// string is built here.
export const fetchPlantObservations = async (plantId, { qcStatus, fields, includeGdd } = {}) => {
  const p = new URLSearchParams({ limit: '5000' });
  if (qcStatus) p.set('qc_status', qcStatus);
  // the back end computes aligned GDD from plant_positions (same definition as the export);
  // days without environment records come back as null.
  if (includeGdd) p.set('include_gdd', 'true');
  (fields || []).filter(Boolean).forEach((f) => p.append('fields', f));
  const r = await api.get(`/plant-view/plants/${plantId}/observations?${p.toString()}`);
  return r.data;
};

// list of single-plant images (stem / ts / DAS / qc_status)
export const fetchPlantFrames = async (plantId) => {
  const r = await api.get(`/plant-view/plants/${plantId}/frames`);
  return r.data;
};

// URL of one single-plant image (for <img src>)
export const plantImageUrl = (plantId, stem) =>
  `${API_BASE}/plant-view/plants/${plantId}/image?stem=${encodeURIComponent(stem)}`;

// URL of one transparent segmentation and assignment overlay (static PNG; 503 when not mounted)
export const plantOverlayUrl = (plantId, stem) =>
  `${API_BASE}/plant-view/plants/${plantId}/overlay?stem=${encodeURIComponent(stem)}`;

// deep link into the review tool; its host comes from VITE_QC_APP_URL, null when unset (button hidden)
export const qcDeepLink = (businessKey) => {
  const base = import.meta.env.VITE_QC_APP_URL;
  return base ? `${base.replace(/\/$/, '')}/?plant=${encodeURIComponent(businessKey)}` : null;
};
