// Presentation helpers shared by every component.
// Status is always rendered as glyph + word, never colour alone.

export const CLASSIFICATION_META = {
  COMPLIANT: { title: 'Compliant', tone: 'ok', glyph: '✓' },
  SELLER_FRAUD: { title: 'Seller-side discrepancy', tone: 'bad', glyph: '!' },
  COUNTERFEIT_OR_ILLEGAL_IMPORT: {
    title: 'Product / official record conflict',
    tone: 'bad',
    glyph: '!',
  },
  MANUAL_REVIEW: { title: 'Manual review', tone: 'unknown', glyph: '?' },
}

export const STATUS_META = {
  PASS: { label: 'Pass', glyph: '✓' },
  FAIL: { label: 'Fail', glyph: '✕' },
  REVIEW: { label: 'Review', glyph: '?' },
  NOT_APPLICABLE: { label: 'N/A', glyph: '–' },
  MATCH: { label: 'Match', glyph: '✓' },
  MISMATCH: { label: 'Mismatch', glyph: '✕' },
  INSUFFICIENT: { label: 'Insufficient', glyph: '?' },
}

export const LAYER_META = {
  PHOTO: { label: 'Physical label', glyph: '▣' },
  LISTING: { label: 'Seller listing', glyph: '▤' },
  OFFICIAL: { label: 'Official record', glyph: '▦' },
}

export function classificationMeta(code) {
  return (
    CLASSIFICATION_META[code] || {
      title: code || 'Not verified',
      tone: 'unknown',
      glyph: '?',
    }
  )
}

export function statusMeta(status) {
  return STATUS_META[status] || { label: status || '—', glyph: '–' }
}

export function pct(value) {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}
