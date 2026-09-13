import { statusMeta } from '../shared.js'

/** Status pill: glyph + word, so it never relies on colour alone. */
export default function Badge({ status }) {
  const meta = statusMeta(status)
  return (
    <span className={`badge b-${String(status || '').toLowerCase()}`}>
      <span className="glyph" aria-hidden="true">
        {meta.glyph}
      </span>
      {meta.label}
    </span>
  )
}
