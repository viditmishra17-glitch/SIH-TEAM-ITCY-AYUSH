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

function VerdictReason({ result, meta }) {
  const failed = result.summary?.failed || 0
  const review = result.summary?.review || 0
  const mismatched = result.summary?.fields_mismatched || 0

  let reason = result.headline || 'The verification pipeline has completed.'

  if (meta.tone === 'ok') {
    reason =
      'The physical label, seller listing and official declaration are consistent with the configured compliance rules.'
  } else if (meta.tone === 'bad' && failed > 0) {
    reason =
      result.headline ||
      `${failed} compliance rule${failed === 1 ? '' : 's'} failed during verification. Review the evidence below to understand the discrepancy.`
  } else if (review > 0) {
    reason =
      result.headline ||
      `${review} rule${review === 1 ? '' : 's'} require manual review because the available evidence is insufficient for a definitive conclusion.`
  }

  return (
    <div className={`verdict-reason tone-${meta.tone}`}>
      <div className="reason-icon" aria-hidden="true">
        {meta.glyph}
      </div>

      <div>
        <span>Why this verdict</span>
        <p>{reason}</p>

        {mismatched > 0 ? (
          <small>
            {mismatched} field{mismatched === 1 ? '' : 's'} show a mismatch
            across the available sources.
          </small>
        ) : null}
      </div>
    </div>
  )
}

/**
 * Primary result hierarchy:
 * 1. Large, unmistakable verdict.
 * 2. One-line explanation of why.
 * 3. Supporting metrics and three-source availability.
 */
export default function VerdictPanel({ result, onReverify, busy }) {
  const meta = classificationMeta(result.classification)

  return (
    <div className="panel verdict-panel">
      <div className="panel-h">
        <div>
          <h2>
            Case {result.case_id}
            {result.is_golden ? ' · seeded demo case' : ''}
          </h2>

          <p className="panel-subtitle">
            Verification result and supporting evidence
          </p>
        </div>

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
        <div className="verdict-hero">
          <div className={`verdict-badge verdict-badge-large tone-${meta.tone}`}>
            <span className="glyph" aria-hidden="true">
              {meta.glyph}
            </span>

            <span>
              <small>VERIFICATION VERDICT</small>
              {meta.title}
            </span>
          </div>

          <div className="verdict-body">
            <p className="verdict-headline">
              {result.headline || 'Verification completed.'}
            </p>

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
                <strong className="mono">
                  {result.product.identifier || '—'}
                </strong>
              </div>

              <div className="metric">
                <span>Findings</span>
                <strong>
                  {result.summary.failed} failed{' '}
                  <small>
                    / {result.summary.review} review
                  </small>
                </strong>
              </div>

              <div className="metric">
                <span>Rule set</span>
                <strong className="mono small">
                  {result.ruleset_version || '—'}
                </strong>
              </div>
            </div>
          </div>
        </div>

        <VerdictReason result={result} meta={meta} />

        <div className="sources-section">
          <div className="section-label">Evidence sources</div>

          <div className="sources">
            {['PHOTO', 'LISTING', 'OFFICIAL'].map((code) => (
              <SourceRow
                key={code}
                code={code}
                source={result.sources[code]}
              />
            ))}
          </div>
        </div>

        <p className="disclaimer">{result.disclaimer}</p>
      </div>
    </div>
  )
}