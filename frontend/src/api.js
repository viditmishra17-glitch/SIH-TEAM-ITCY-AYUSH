// Thin API client. Every call goes through here so the base URL is set once:
// empty (same origin) when FastAPI serves the bundle, or the Render URL when
// the frontend is deployed separately on Vercel.

const RAW_BASE = import.meta.env.VITE_API_BASE_URL || ''
export const API_BASE = RAW_BASE.replace(/\/+$/, '')

export function apiUrl(path) {
  if (!path) return API_BASE || '/'
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(apiUrl(path), options)
  } catch (cause) {
    throw new ApiError(
      'Could not reach the TriVerify API. Is the backend running?',
      0,
    )
  }

  const isJson = (response.headers.get('content-type') || '').includes('application/json')
  const payload = isJson ? await response.json().catch(() => null) : null

  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.message)) ||
      `Request failed with status ${response.status}.`
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), response.status)
  }
  return payload
}

export const getHealth = () => request('/health')

export const listCases = (params = {}) => {
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.classification) search.set('classification', params.classification)
  const qs = search.toString()
  return request(`/cases${qs ? `?${qs}` : ''}`)
}

export const getCase = (caseId) => request(`/cases/${encodeURIComponent(caseId)}`)

export const reverifyCase = (caseId) =>
  request(`/cases/${encodeURIComponent(caseId)}/verify`, { method: 'POST' })

export const getEvidence = (caseId, evidenceId) =>
  request(`/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}`)

export const getRules = () => request('/rules')

export async function createCase({ file, identifier, productName, brand, category }) {
  const form = new FormData()
  form.append('image', file)
  form.append('identifier', identifier)
  if (productName) form.append('product_name', productName)
  if (brand) form.append('brand', brand)
  if (category) form.append('category', category)
  return request('/cases', { method: 'POST', body: form })
}

export const reportUrl = (caseId, format = 'html') =>
  apiUrl(`/cases/${encodeURIComponent(caseId)}/report?format=${format}`)

export { ApiError }
