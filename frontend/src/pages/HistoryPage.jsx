import { useEffect, useState } from 'react'
import { listCases } from '../api.js'
import { classificationMeta, formatDate, pct } from '../shared.js'

const CLASSIFICATIONS = [
  '',
  'COMPLIANT',
  'SELLER_FRAUD',
  'COUNTERFEIT_OR_ILLEGAL_IMPORT',
  'MANUAL_REVIEW',
]

export default function HistoryPage({ navigate }) {
  const [query, setQuery] = useState('')
  const [classification, setClassification] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    // Debounced so typing does not fire a request per keystroke.
    const timer = setTimeout(() => {
      listCases({ q: query, classification })
        .then((data) => {
          if (cancelled) return
          setItems(data.items || [])
          setTotal(data.total || 0)
          setError(null)
        })
        .catch((err) => !cancelled && setError(err.message))
        .finally(() => !cancelled && setLoading(false))
    }, 220)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, classification])

  return (
    <div className="panel">
      <div className="panel-h">
        <h2>Inspection history</h2>
        <span className="spacer" />
        <span className="small muted">{total} case{total === 1 ? '' : 's'}</span>
      </div>
      <div className="panel-b">
        <div className="row" style={{ marginBottom: 14 }}>
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search case id, product, brand or identifier"
            aria-label="Search cases"
            style={{
              flex: '1 1 280px',
              padding: '8px 10px',
              border: '1px solid var(--line)',
              borderRadius: 6,
            }}
          />
          <select
            value={classification}
            onChange={(event) => setClassification(event.target.value)}
            aria-label="Filter by classification"
            style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6 }}
          >
            {CLASSIFICATIONS.map((code) => (
              <option key={code} value={code}>
                {code ? classificationMeta(code).title : 'All classifications'}
              </option>
            ))}
          </select>
        </div>

        {error ? <div className="alert error">{error}</div> : null}

        {loading && items.length === 0 ? (
          <p className="center">Loading cases…</p>
        ) : items.length === 0 ? (
          <p className="center">No cases match. Try clearing the filters.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="list">
              <thead>
                <tr>
                  <th scope="col">Case</th>
                  <th scope="col">Product</th>
                  <th scope="col">Identifier</th>
                  <th scope="col">Classification</th>
                  <th scope="col">Conf.</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Created</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const meta = classificationMeta(item.classification)
                  return (
                    <tr
                      key={item.case_id}
                      onClick={() => navigate(`/case/${item.case_id}`)}
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') navigate(`/case/${item.case_id}`)
                      }}
                    >
                      <td className="mono">
                        <b>{item.case_id}</b>
                      </td>
                      <td>
                        {item.product_name || '—'}
                        {item.brand ? <span className="muted small"> · {item.brand}</span> : null}
                      </td>
                      <td className="mono small">{item.identifier || '—'}</td>
                      <td>
                        <span
                          className={`badge b-${
                            meta.tone === 'ok' ? 'pass' : meta.tone === 'bad' ? 'fail' : 'review'
                          }`}
                        >
                          <span className="glyph" aria-hidden="true">
                            {meta.glyph}
                          </span>
                          {meta.title}
                        </span>
                      </td>
                      <td>{pct(item.overall_confidence)}</td>
                      <td className="small">
                        {item.failed_rules} failed
                        {item.top_severity ? ` · ${item.top_severity}` : ''}
                      </td>
                      <td className="small">{formatDate(item.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
