import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_APP_API_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error('API Response Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// B2 collapse: single mount /api/v1. `apiV2` kept as an alias of the one client
// so existing `import { apiV2 }` sites keep working; the v2 name is now cosmetic.
export { api as apiV2 };
export default api;