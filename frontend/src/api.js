// Thin API client. Every call goes through here so the base URL is set once.
//
// Resolution order:
//   1. ?api=https://host     one-off override, remembered for this tab
//   2. window.__PARAKH_API_BASE__
//   3. VITE_API_BASE_URL     inlined by Vite at BUILD time
//   4. ''                    same origin (FastAPI serving the bundle)
//
// Step 3 is the usual production path and the usual production mistake: Vite
// inlines VITE_* when the bundle is compiled, so setting it in a hosting
// dashboard AFTER a deploy changes nothing until you rebuild. When that
// happens every call silently goes to the static host instead of the API, so
// request() below detects it and says so rather than reporting a bare 404.

function readRuntimeBase() {
  if (typeof window === 'undefined') return ''
  try {
    const fromQuery = new URLSearchParams(window.location.search).get('api')
    if (fromQuery !== null) {
      const trimmed = fromQuery.trim()
      if (trimmed) window.sessionStorage.setItem('parakh.apiBase', trimmed)
      else window.sessionStorage.removeItem('parakh.apiBase')
      return trimmed
    }
    const stored = window.sessionStorage.getItem('parakh.apiBase')
    if (stored) return stored
    if (window.__PARAKH_API_BASE__) return String(window.__PARAKH_API_BASE__)
  } catch {
    // Private browsing or storage disabled - fall back to the build-time value.
  }
  return ''
}

const RAW_BASE = readRuntimeBase() || import.meta.env.VITE_API_BASE_URL || ''
export const API_BASE = RAW_BASE.replace(/\/+$/, '')

export function apiUrl(path) {
  if (!path) return API_BASE || '/'
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

class ApiError extends Error {
  constructor(message, status, userMessage = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.userMessage = userMessage
  }
}

function friendlyApiMessage(status, detail) {
  const raw =
    typeof detail === 'string'
      ? detail
      : detail
        ? JSON.stringify(detail)
        : ''

  if (status === 0) {
    return 'Could not reach the PARAKH API. Make sure the backend is running.'
  }

  if (status === 404) {
    return 'The requested PARAKH record could not be found. Check the case or identifier and try again.'
  }

  if (status === 413) {
    return 'The uploaded image is too large. Please choose an image smaller than 12 MB.'
  }

  if (status === 415) {
    return 'This image format is not supported. Please use PNG, JPEG, WEBP, BMP or TIFF.'
  }

  if (status === 422) {
    if (/identifier/i.test(raw)) {
      return 'The product identifier is missing or invalid. Check the barcode/EAN/SKU and try again.'
    }

    if (/image|photograph|decode|file/i.test(raw)) {
      return 'The package photograph could not be processed. Try a clearer image with the label fully visible.'
    }

    return raw || 'Some of the submitted information could not be processed. Check the details and try again.'
  }

  if (status >= 500) {
    return 'The verification service encountered an internal problem. Please retry the verification.'
  }

  return raw || `The request could not be completed (HTTP ${status}).`
}

async function request(path, options = {}) {
  let response

  try {
    response = await fetch(apiUrl(path), options)
  } catch (cause) {
    throw new ApiError(
      'Could not reach the PARAKH API. Is the backend running?',
      0,
      'PARAKH could not reach the verification service. Make sure the backend is running and try again.',
    )
  }

  const isJson = (response.headers.get('content-type') || '').includes(
    'application/json',
  )

  const payload = isJson
    ? await response.json().catch(() => null)
    : null

  if (!response.ok) {
    // A 404 that is NOT JSON means we hit a static host with no API behind it:
    // the bundle was built without an API address, so calls went to this
    // site's own origin. FastAPI always answers with JSON, so this cannot
    // misfire when the backend really is serving the page.
    if (response.status === 404 && !isJson && !API_BASE) {
      throw new ApiError(
        'No API base URL is configured in this build.',
        0,
        'PARAKH has no backend address configured, so requests are going to this ' +
          'site itself. Set VITE_API_BASE_URL to the backend URL and redeploy - ' +
          'or add ?api=https://your-backend-url to this page to test right now.',
      )
    }

    const detail =
      payload && (payload.detail || payload.message)

    const rawMessage =
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `Request failed with status ${response.status}.`

    throw new ApiError(
      rawMessage,
      response.status,
      friendlyApiMessage(response.status, detail),
    )
  }

  return payload
}

export const getHealth = () => request('/health')

export const listCases = (params = {}) => {
  const search = new URLSearchParams()

  if (params.q) search.set('q', params.q)
  if (params.classification) {
    search.set('classification', params.classification)
  }

  const qs = search.toString()

  return request(`/cases${qs ? `?${qs}` : ''}`)
}

export const getCase = (caseId) =>
  request(`/cases/${encodeURIComponent(caseId)}`)

export const reverifyCase = (caseId) =>
  request(`/cases/${encodeURIComponent(caseId)}/verify`, {
    method: 'POST',
  })

export const getEvidence = (caseId, evidenceId) =>
  request(
    `/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(
      evidenceId,
    )}`,
  )

export const getRules = () => request('/rules')

export async function createCase({
  file,
  identifier,
  productName,
  brand,
  category,
}) {
  const form = new FormData()

  form.append('image', file)
  form.append('identifier', identifier)

  if (productName) {
    form.append('product_name', productName)
  }

  if (brand) {
    form.append('brand', brand)
  }

  if (category) {
    form.append('category', category)
  }

  return request('/cases', {
    method: 'POST',
    body: form,
  })
}

export const reportUrl = (caseId, format = 'html') =>
  apiUrl(
    `/cases/${encodeURIComponent(caseId)}/report?format=${format}`,
  )

export { ApiError }