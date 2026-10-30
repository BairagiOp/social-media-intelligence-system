import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

function extractError(err) {
  if (err.response) {
    const data = err.response.data || {}
    return {
      status: err.response.status,
      code: data.code || 'error',
      detail: data.detail || `Request failed (HTTP ${err.response.status})`,
    }
  }
  if (err.request) {
    return {
      status: 0,
      code: 'backend_unavailable',
      detail: 'Backend unavailable. Start the API server (uvicorn app.main:app) and retry.',
    }
  }
  return { status: 0, code: 'client_error', detail: err.message }
}

export async function request(method, url, { params, data, signal } = {}) {
  try {
    const resp = await api.request({ method, url, params, data, signal })
    return resp.data
  } catch (err) {
    throw extractError(err)
  }
}

export const get = (url, params) => request('GET', url, { params })
export const post = (url, data, params) => request('POST', url, { data, params })
export const del = (url) => request('DELETE', url)

// ---- typed API surface -------------------------------------------------
export const apiClient = {
  health: () => get('/health'),
  meta: () => get('/meta'),
  dashboard: (datasetId) =>
    get('/dashboard/summary', datasetId ? { dataset_id: datasetId } : undefined),

  listDatasets: () => get('/datasets'),
  getDataset: (id) => get(`/datasets/${id}`),
  getProfile: (id, refresh = false) =>
    get(`/datasets/${id}/profile`, refresh ? { refresh: true } : undefined),
  uploadDataset: (file, name) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    return request('POST', '/datasets/upload', { data: form })
  },
  loadSample: () => post('/datasets/sample'),
  preprocess: (id, options) => post(`/datasets/${id}/preprocess`, { options }),
  setColumnMap: (id, mapping) => post(`/datasets/${id}/column-map`, { mapping }),
  deleteDataset: (id) => del(`/datasets/${id}`),
  queryRows: (id, query) => get(`/datasets/${id}/rows`, query),
  discovery: () => get('/datasets/discovery'),

  // --- Web collection (public sources only) ---
  sources: () => get('/datasets/sources'),
  fetchDataset: (payload) => post('/datasets/fetch', payload),
  collectFrom: (payload) => post('/datasets/collect', payload),
  crawlSite: (payload) => post('/datasets/crawl', payload),

  listEvidence: () => get('/evidence'),
  getEvidence: (id) => get(`/evidence/${id}`),
  auditLog: (id) => get(`/evidence/${id}/audit-log`),
  exportEvidence: (id) => get(`/evidence/${id}/export`),

  sentiment: (datasetId) => post('/analysis/sentiment', { dataset_id: datasetId }),
  topics: (datasetId, nTopics = 6, topTerms = 10) =>
    post('/analysis/topics', { dataset_id: datasetId, n_topics: nTopics, top_terms: topTerms }),
  bot: (datasetId) => post('/analysis/bot', { dataset_id: datasetId }),
  misinformation: (datasetId, limit = 500) =>
    post('/analysis/misinformation', { dataset_id: datasetId, limit }),
  inference: (payload) => post('/analysis/inference', payload),

  graph: (params) => get('/network/graph', params),

  mlTasks: () => get('/ml/tasks'),
  train: (payload) => post('/ml/train', payload),
  job: (jobId) => get(`/ml/jobs/${jobId}`),
  models: (task) => get('/ml/models', task ? { task } : undefined),
  model: (ref) => get(`/ml/models/${ref}`),
  activateModel: (ref) => post(`/ml/models/${ref}/activate`),
  archiveModel: (ref) => post(`/ml/models/${ref}/archive`),
  activeModels: () => get('/ml/active'),

  reports: () => get('/reports'),
  createReport: (payload) => post('/reports', payload),
  getReport: (id) => get(`/reports/${id}`),
}

export default apiClient
