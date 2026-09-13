import { useEffect, useState } from 'react'
import { apiUrl, getEvidence } from '../api.js'
import { LAYER_META, formatDateTime, pct } from '../shared.js'

/**
 * The single "Evidence" action from the manual: what was observed, where it
 * came from, and the untouched source payload behind it.
 */
export default function EvidenceDrawer({ caseId, evidenceId, onClose }) {
  const [state, setState] = useState({ loading: true, error: null, data: null })

  useEffect(() => {
    let cancelled = false
    setState({ loading: true, error: null, data: null })
    getEvidence(caseId, evidenceId)
      .then((data) => {
        if (!cancelled) setState({ loading: false, error: null, data })
      })
      .catch((error) => {
        if (!cancelled) setState({ loading: false, error: error.message, data: null })
      })
    return () => {
      cancelled = true
    }
  }, [caseId, evidenceId])

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const data = state.data
  const layer = data ? LAYER_META[data.source_type] : null
  const raw = data?.metadata?.raw_snapshot || data?.metadata?.raw_record || null

  return (
    <div
      className="drawer-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Evidence ${evidenceId}`}
    >
      <div className="drawer" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-h">
          <h3>Evidence {evidenceId}</h3>
          <button type="button" className="close" onClick={onClose} aria-label="Close evidence">
            ✕
          </button>
        </div>
        <div className="drawer-b">
          {state.loading ? <p className="center">Loading evidence…</p> : null}
          {state.error ? <div className="alert error">{state.error}</div> : null}

          {data ? (
            <>
              {data.has_crop && data.crop_url ? (
                <div className="crop">
                  <img
                    src={apiUrl(data.crop_url)}
                    alt={`Cropped region of the label showing ${data.field_name}`}
                  />
                  <p className="small muted" style={{ margin: '8px 0 0' }}>
                    Cut from the original uploaded photograph at the bounding box the
                    extractor recorded.
                  </p>
                </div>
              ) : null}

              <dl className="kv">
                <dt>Source</dt>
                <dd>
                  <span aria-hidden="true">{layer?.glyph} </span>
                  {layer?.label || data.source_type}
                </dd>

                <dt>Field</dt>
                <dd className="mono">{data.field_name || '—'}</dd>

                <dt>Raw value</dt>
                <dd>“{data.raw_value ?? '—'}”</dd>

                <dt>Normalized</dt>
                <dd>{data.display || '—'}</dd>

                <dt>Confidence</dt>
                <dd>{pct(data.confidence)}</dd>

                <dt>Captured</dt>
                <dd>{formatDateTime(data.captured_at)}</dd>

                <dt>Reference</dt>
                <dd className="small mono">{data.source_ref || '—'}</dd>

                {data.bbox ? (
                  <>
                    <dt>Region</dt>
                    <dd className="small mono">
                      x{Math.round(data.bbox[0])} y{Math.round(data.bbox[1])} ·{' '}
                      {Math.round(data.bbox[2])}×{Math.round(data.bbox[3])} px
                    </dd>
                  </>
                ) : null}
              </dl>

              {data.normalized_value ? (
                <>
                  <p
                    className="small muted"
                    style={{ margin: '18px 0 0', fontWeight: 700 }}
                  >
                    NORMALIZED VALUE
                  </p>
                  <pre className="raw">{JSON.stringify(data.normalized_value, null, 2)}</pre>
                </>
              ) : null}

              {raw ? (
                <>
                  <p
                    className="small muted"
                    style={{ margin: '18px 0 0', fontWeight: 700 }}
                  >
                    RAW SOURCE PAYLOAD
                  </p>
                  <pre className="raw">{JSON.stringify(raw, null, 2)}</pre>
                </>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
