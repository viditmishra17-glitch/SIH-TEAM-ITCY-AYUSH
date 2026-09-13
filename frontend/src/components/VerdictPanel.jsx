import { classificationMeta, formatDateTime, LAYER_META, pct } from '../shared.js'
import { reportUrl } from '../api.js'

function SourceRow({ code, source }) {
  const meta = LAYER_META[code]
  const ok = source?.available
  return (
    <div className={`source${ok ? '' : ' off'}`}>
      <span className="glyph" aria-hidden="true">
        {ok ? meta.glyph : '⚠'}
      </span>
      <div>
        <b>
          {meta.label} — {ok ? 'available' : 'unavailable'}
        </b>
        <small>
          {ok
            ? `${source.source || 'source'}${
                source.is_live ? ' · live' : ' · cached snapshot'
              } · captured ${formatDateTime(source.captured_at)}`
            : source?.note || 'Not supplied.'}
        </small>
      </div>
    </div>
  )
}

/** Demo hierarchy step 1 & 2: big classification, one-sentence reason. */
export default function VerdictPanel({ result, onReverify, busy }) {
  const meta = classificationMeta(result.classification)

  return (
    <div className="panel">
      <div className="panel-h">
        <h2>
          Case {result.case_id}
          {result.is_golden ? ' · seeded demo case' : ''}
        </h2>
        <span className="spacer" />
        <div className="row">
          <button
            type="button"
            className="btn ghost sm"
            onClick={onReverify}
            disabled={busy}
          >
            {busy ? 'Re-running…' : 'Re-run verification'}
          </button>
          <a
            className="btn sm"
            href={reportUrl(result.case_id, 'html')}
            target="_blank"
            rel="noreferrer"
          >
            Generate report
          </a>
          <a
            className="btn ghost sm"
            href={reportUrl(result.case_id, 'pdf')}
            target="_blank"
            rel="noreferrer"
          >
            PDF
          </a>
        </div>
      </div>

      <div className="panel-b">
        <div className="verdict">
          <div className={`verdict-badge tone-${meta.tone}`}>
            <span className="glyph" aria-hidden="true">
              {meta.glyph}
            </span>
            {meta.title}
          </div>

          <div className="verdict-body">
            <p>{result.headline}</p>
            <div className="metrics">
              <div className="metric">
                <span>Confidence</span>
                <strong>{pct(result.overall_confidence)}</strong>
              </div>
              <div className="metric">
                <span>Product</span>
                <strong>{result.product.name || '—'}</strong>
              </div>
              <div className="metric">
                <span>Identifier</span>
                <strong className="mono">{result.product.identifier || '—'}</strong>
              </div>
              <div className="metric">
                <span>Findings</span>
                <strong>
                  {result.summary.failed} failed{' '}
                  <small>/ {result.summary.review} review</small>
                </strong>
              </div>
              <div className="metric">
                <span>Rule set</span>
                <strong className="mono small">{result.ruleset_version || '—'}</strong>
              </div>
            </div>
          </div>
        </div>

        <div className="sources" style={{ marginTop: 18 }}>
          {['PHOTO', 'LISTING', 'OFFICIAL'].map((code) => (
            <SourceRow key={code} code={code} source={result.sources[code]} />
          ))}
        </div>

        <p className="disclaimer">{result.disclaimer}</p>
      </div>
    </div>
  )
}
