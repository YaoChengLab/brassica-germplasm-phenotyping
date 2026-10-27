/**
 * v2 Query Service — all API calls use apiV2 instance.
 * New: fields parameter for observation endpoints,
 *      maxPoints for time-series endpoints.
 */
import { apiV2 } from './api';

// ========================================
// Search
// ========================================

export const fetchSearchResults = async (query, isAdvanced = false) => {
  let payload;
  if (isAdvanced) {
    payload = {
      filters: query.filters,
      logic: query.logic || 'AND',
      limit: query.limit,
      offset: query.offset,
    };
  } else {
    payload = {
      product_name_filters: query.product_name_filters || [],
      cultivar_code_filters: query.cultivar_code_filters || [],
      search_term: query.search_term,
      limit: query.limit,
      offset: query.offset,
    };
  }

  const response = await apiV2.post('/query/cultivars/search', payload);
  return response.data;
};

// ========================================
// Cultivar data
// ========================================

export const fetchCultivarTimeSeriesData = async (cultivarId, { maxPoints } = {}) => {
  const params = {};
  if (maxPoints) params.max_points = maxPoints;

  const response = await apiV2.get(`/query/cultivars/${cultivarId}/time-series`, { params });
  return response.data;
};

export const fetchCultivarDetails = async (cultivarId) => {
  const response = await apiV2.get(`/query/cultivars/${cultivarId}/details`);
  return response.data;
};

export const fetchCultivarChamberTimeline = async (cultivarCode) => {
  const response = await apiV2.get(`/query/cultivars/${cultivarCode}/chamber-timeline`);
  return response.data;
};

export const fetchCultivarSignatureTraits = async (cultivarCode) => {
  const response = await apiV2.get(`/query/cultivars/${cultivarCode}/signature-traits`);
  return response.data;
};

export const fetchCultivarImages = async (cultivarCode) => {
  const response = await apiV2.get(`/query/cultivars/${cultivarCode}/images`);
  return response.data;
};

// ========================================
// Batches
// ========================================

export const fetchBatchesWithCultivars = async () => {
  const response = await apiV2.get('/query/batches/with-cultivars');
  return response.data;
};

// ========================================
// Plant observations (with fields support)
// ========================================

export const fetchPlantObservations = async (plantId, { observationType, fields, limit, offset } = {}) => {
  const params = {};
  if (observationType) params.observation_type = observationType;
  if (fields) params.fields = fields.join(',');
  if (limit) params.limit = limit;
  if (offset) params.offset = offset;

  const response = await apiV2.get(`/query/plants/${plantId}/observations`, { params });
  return response.data;
};

export const fetchObservationsWithEnvironment = async (plantId, { fields } = {}) => {
  const params = {};
  if (fields) params.fields = fields.join(',');

  const response = await apiV2.get(`/query/plants/${plantId}/observations-with-environment`, { params });
  return response.data;
};

// ========================================
// Database & Environment
// ========================================

export const fetchDatabaseSummary = async () => {
  const response = await apiV2.get('/query/plant/summary');
  return response.data;
};

export const fetchFilterOptions = async () => {
  const response = await apiV2.get('/query/cultivars/filter-options');
  return response.data;
};

export const fetchEnvironmentSensors = async () => {
  const response = await apiV2.get('/query/environment/sensors');
  return response.data;
};

export const fetchEnvironmentObservations = async (params) => {
  const response = await apiV2.get('/query/environment/observations', { params });
  return response.data;
};
