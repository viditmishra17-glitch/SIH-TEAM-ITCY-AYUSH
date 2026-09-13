import { useMemo, useState } from 'react'
import Badge from './Badge.jsx'
import { pct } from '../shared.js'

const FILTERS = [
  { key: 'ACTION', label: 'Needs attention' },
  { key: 'FAIL', label: 'Failed' },
  { key: 'REVIEW', label: 'Review' },
  { key: 'PASS', label: 'Passed' },
  { key: 'ALL', label: 'All' },
]

/** Right pane: rule-by-rule detail, each linked to its evidence. */
export default function FindingsPanel({
  result,
  onOpenEvidence,
  onSelectField,
  activeField,
}) {
  const [filter, setFilter] = useState('ACTION')

  const findings = useMemo(() => {
    const all = result.findings || []
    if (filter === 'ALL') return all
    if (filter === 'ACTION') return all.filter((f) => f.status === 'FAIL' || f.status === 'REVIEW')
    return all.filter((f) => f.status === filter)
  }, [result.findings, filter])

  const { passed, failed, review, not_applicable: na } = result.summary

  return (
    <div className="panel">
      <div className="panel-h">
        <h2>Rule findings</h2>
        <span className="spacer" />
        <span className="small muted">
          {failed} fail · {review} review · {passed} pass · {na} n/a
        </span>
      </div>
      <div className="panel-b">
        <div className="filters" role="group" aria-label="Filter findings">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={filter === item.key}
              onClick={() => setFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {findings.length === 0 ? (
          <p className="center small">
            {filter === 'ACTION'
              ? 'Nothing needs attention — every configured rule passed.'
              : 'No findings in this category.'}
          </p>
        ) : (
          <ul className="findings">
            {findings.map((finding) => (
              <li
                key={finding.rule_id}
                className="finding"
                style={
                  activeField && finding.field_name === activeField
                    ? { background: '#f4f8fd', marginInline: -15, paddingInline: 15 }
                    : undefined
                }
              >
                <div className="finding-h">
                  <Badge status={finding.status} />
                  <span className="rule-id">{finding.rule_id}</span>
                  <span className="sev">{finding.severity}</span>
                  <span className="spacer" style={{ marginLeft: 'auto' }} />
                  <span className="sev">conf {pct(finding.confidence)}</span>
                </div>
                <p>{finding.explanation}</p>
                <div className="ev-row">
                  {finding.field_name ? (
                    <button
                      type="button"
                      className="chip"
                      onClick={() => onSelectField(finding.field_name)}
                      title="Highlight this field"
                    >
                      ▸ {finding.field_name}
                    </button>
                  ) : null}
                  {(finding.evidence_ids || []).map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="chip"
                      onClick={() => onOpenEvidence(id)}
                      title="Open the underlying evidence"
                    >
                      {id}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
