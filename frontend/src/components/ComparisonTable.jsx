import Badge from './Badge.jsx'
import { LAYER_META, pct } from '../shared.js'

function Cell({ value, fieldName, onOpenEvidence }) {
  if (!value || !value.available) {
    return (
      <td className="val">
        <span className="none">not declared</span>
      </td>
    )
  }
  const showRaw = value.raw && value.display && value.raw !== value.display
  return (
    <td className="val">
      <span>{value.display || value.raw}</span>
      {showRaw ? <span className="raw">read as: “{value.raw}”</span> : null}
      {typeof value.confidence === 'number' && value.confidence < 1 ? (
        <span className="conf">confidence {pct(value.confidence)}</span>
      ) : null}
      {value.evidence_id ? (
        <button
          type="button"
          className="ev-link"
          onClick={(event) => {
            event.stopPropagation()
            onOpenEvidence(value.evidence_id)
          }}
        >
          Evidence {value.evidence_id}
        </button>
      ) : null}
    </td>
  )
}

/** Middle pane: the three-layer comparison that is the core of the argument. */
export default function ComparisonTable({
  result,
  activeField,
  onSelectField,
  onOpenEvidence,
}) {
  const mismatches = result.summary.fields_mismatched

  return (
    <div className="panel">
      <div className="panel-h">
        <h2>Three-layer comparison</h2>
        <span className="spacer" />
        <span className="small muted">
          {result.summary.fields_compared} compared · {mismatches} mismatched
        </span>
      </div>
      <div className="panel-b" style={{ overflowX: 'auto' }}>
        <table className="cmp">
          <thead>
            <tr>
              <th scope="col">Declaration</th>
              <th scope="col">{LAYER_META.PHOTO.label}</th>
              <th scope="col">{LAYER_META.LISTING.label}</th>
              <th scope="col">{LAYER_META.OFFICIAL.label}</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {result.field_order.map((name) => {
              const field = result.fields[name]
              const isActive = activeField === name
              return (
                <tr
                  key={name}
                  className={isActive ? 'is-active' : ''}
                  onClick={() => onSelectField(isActive ? null : name)}
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onSelectField(isActive ? null : name)
                    }
                  }}
                  aria-selected={isActive}
                >
                  <td className="decl">
                    {field.label}
                    {field.is_material ? (
                      <span className="material" title="Can drive the classification">
                        material
                      </span>
                    ) : null}
                  </td>
                  <Cell
                    value={field.photo}
                    fieldName={name}
                    onOpenEvidence={onOpenEvidence}
                  />
                  <Cell
                    value={field.listing}
                    fieldName={name}
                    onOpenEvidence={onOpenEvidence}
                  />
                  <Cell
                    value={field.official}
                    fieldName={name}
                    onOpenEvidence={onOpenEvidence}
                  />
                  <td>
                    <Badge status={field.status} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {activeField && result.fields[activeField]?.note ? (
          <p className="small muted" style={{ marginTop: 12 }}>
            <strong>{result.fields[activeField].label}:</strong>{' '}
            {result.fields[activeField].note}
          </p>
        ) : null}
      </div>
    </div>
  )
}
