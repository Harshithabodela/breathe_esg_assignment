import axios from 'axios';

function getCsrfToken() {
  const name = 'csrftoken';
  for (let cookie of document.cookie.split(';')) {
    const trimmed = cookie.trim();
    if (trimmed.startsWith(name + '=')) {
      return decodeURIComponent(trimmed.slice(name.length + 1));
    }
  }
  return null;
}

// In production (Render static site), VITE_API_BASE_URL points to the API service.
// In local dev, Vite's proxy forwards /api/* to localhost:8000, so baseURL stays ''.
const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const client = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

client.interceptors.request.use((config) => {
  if (config.method && config.method.toLowerCase() !== 'get') {
    const token = getCsrfToken();
    if (token) config.headers['X-CSRFToken'] = token;
  }
  return config;
});

export function login(username, password) {
  return client.post('/api/auth/login/', { username, password });
}

export function logout() {
  return client.post('/api/auth/logout/');
}

export function getMe() {
  return client.get('/api/auth/me/');
}

export function getIngestions() {
  return client.get('/api/ingestions/');
}

export function uploadFile(file, source_type) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('source_type', source_type);
  return client.post('/api/ingestions/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export function getActivityRecords(params = {}) {
  return client.get('/api/activity-records/', { params });
}

export function getActivitySummary() {
  return client.get('/api/activity-records/summary/');
}

export function approveRecord(id, note = '') {
  return client.post(`/api/activity-records/${id}/approve/`, { note });
}

export function flagRecord(id, reason) {
  return client.post(`/api/activity-records/${id}/flag/`, { reason });
}

export function lockRecord(id) {
  return client.post(`/api/activity-records/${id}/lock/`);
}

export function editRecord(id, data) {
  return client.patch(`/api/activity-records/${id}/edit/`, data);
}

export function getRecord(id) {
  return client.get(`/api/activity-records/${id}/`);
}

export function bulkApprove(ids) {
  return client.post('/api/activity-records/bulk-approve/', { ids });
}

export default client;
