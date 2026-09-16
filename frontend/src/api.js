// Thin API client. Every call goes through here so the base URL is set once.
//
// Resolution order, first non-empty wins:
//   1. ?api=https://host              one-off override, then remembered
//   2. saved override                 localStorage, set from the UI or by (1)
//   3. window.__PARAKH_API_BASE__     public/config.js - editable after build
//   4. VITE_API_BASE_URL              inlined by Vite at BUILD time
//   5. ''                             same origin (FastAPI serving the bundle)
//
// Step 4 is the usual production mistake: Vite inlines VITE_* when the bundle
// is COMPILED, so setting it in a hosting dashboard after a deploy changes
// nothing until you rebuild. Steps 1-3 exist so the app can be repointed
// without a rebuild, and request() below names the problem instead of
// reporting a bare 404.

const STORAGE_KEY = 'parakh.apiBase'

// The app uses hash routing, so a pasted "?api=" usually lands INSIDE the hash
// (".../#/?api=https://host"), where location.search is empty. Read both.
function readParam(name) {
  const fromSearch = new URLSearchParams(window.location.search).get(name)
  if (fromSearch !== null) return fromSearch

  const hash = window.location.hash || ''
  const mark = hash.indexOf('?')
  if (mark === -1) return null

  return new URLSearchParams(hash.slice(mark + 1)).get(name)
}

// localStorage first so the override survives a reload, sessionStorage as a
// fallback, and neither is fatal: private browsing makes both throw.
function storage() {
  for (const name of ['localStorage', 'sessionStorage']) {
    try {
      const store = window[name]
      const probe = '__parakh_probe__'
      store.setItem(probe, '1')
      store.removeItem(probe)
      return store
    } catch {
      // Try the next one.
    }
  }
  return null
}

// Accept "host.onrender.com" as well as a full URL, and drop trailing slashes
// so apiUrl() never produces a double slash. A scheme-less address gets https,
// except on the loopback host, which is never served over TLS in development.
const LOOPBACK = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i

export function normalizeBase(value) {
  const trimmed = String(value ?? '').trim()
  if (!trimmed) return ''

  if (/^https?:\/\//i.test(trimmed)) return trimmed.replace(/\/+$/, '')

  const bare = trimmed.replace(/^\/+/, '')
  const host = bare.split('/')[0]
  const scheme = LOOPBACK.test(host) ? 'http' : 'https'

  return `${scheme}://${bare}`.replace(/\/+$/, '')
}

function resolveBase() {
  if (typeof window === 'undefined') {
    return { base: '', source: 'server' }
  }

  const store = storage()

  const fromQuery = readParam('api')
  if (fromQuery !== null) {
    const normalized = normalizeBase(fromQuery)
    try {
      if (normalized) store?.setItem(STORAGE_KEY, normalized)
      else store?.removeItem(STORAGE_KEY)
    } catch {
      // Not being able to remember it does not stop this page load using it.
    }
    if (normalized) return { base: normalized, source: 'query' }
  }

  try {
    const saved = normalizeBase(store?.getItem(STORAGE_KEY))
    if (saved) return { base: saved, source: 'saved' }
  } catch {
    // Ignore and fall through.
  }

  const fromConfig = normalizeBase(window.__PARAKH_API_BASE__)
  if (fromConfig) return { base: fromConfig, source: 'config.js' }

  const fromBuild = normalizeBase(import.meta.env.VITE_API_BASE_URL)
  if (fromBuild) return { base: fromBuild, source: 'build' }

  return { base: '', source: 'same-origin' }
}

const resolved = resolveBase()

export const API_BASE = resolved.base

// Where the address came from. Shown in the UI so a misconfigured deploy is
// diagnosable without opening DevTools.
export const API_BASE_SOURCE = resolved.source

// Save a backend address and reload, since API_BASE is read once at startup.
export function setApiBase(value) {
  const normalized = normalizeBase(value)
  const store = storage()

  try {
    if (normalized) store?.setItem(STORAGE_KEY, normalized)
    else store?.removeItem(STORAGE_KEY)
  } catch {
    // Fall through to the reload; the query-string path still works.
  }

  // Strip any ?api= from the URL so the saved value is what takes effect.
  const clean = window.location.href
    .replace(/([?&])api=[^&#]*/g, '$1')
    .replace(/[?&]$/, '')

  window.location.replace(clean)
  window.location.reload()
}

export function clearApiBase() {
  setApiBase('')
}

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
        'PARAKH has no backend address configured, so requests are going to ' +
          'this site itself instead of the API. Enter the backend URL in the ' +
          'banner at the top of the page to fix it now.',
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