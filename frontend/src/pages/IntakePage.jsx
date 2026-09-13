import { useEffect, useState } from 'react'
import { createCase, listCases } from '../api.js'
import { classificationMeta } from '../shared.js'

/**
 * Case intake. Also surfaces the seeded golden cases, so the demo can reach
 * the evidence view in one click even if an upload misbehaves — the manual's
 * "fallback seeded case openable in under 10 seconds".
 */
export default function IntakePage({ navigate }) {
  const [file, setFile] = useState(null)
  const [identifier, setIdentifier] = useState('')
  const [productName, setProductName] = useState('')
  const [brand, setBrand] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [golden, setGolden] = useState([])

  useEffect(() => {
    listCases()
      .then((data) => setGolden((data.items || []).filter((item) => item.is_golden)))
      .catch(() => setGolden([]))
  }, [])

  const onSubmit = async (event) => {
    event.preventDefault()
    setError(null)
    if (!file) {
      setError('Select a photograph of the package first.')
      return
    }
    if (!identifier.trim()) {
      setError('A product identifier is required to locate the seller and official records.')
      return
    }
    setBusy(true)
    try {
      const created = await createCase({
        file,
        identifier: identifier.trim(),
        productName: productName.trim(),
        brand: brand.trim(),
      })
      navigate(`/case/${created.case_id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-h">
          <h2>New verification case</h2>
        </div>
        <div className="panel-b">
          {error ? <div className="alert error">{error}</div> : null}

          <form className="form" onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="image">Package photograph</label>
              <input
                id="image"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
              <p className="hint">
                PNG, JPEG, WEBP, BMP or TIFF. The original is stored untouched; the
                preprocessed copy is used only for extraction.
                <br />
                For a guaranteed-offline run, upload one of the label images in{' '}
                <code>data/images/</code> — those ship with committed OCR output, so
                extraction is identical on every machine.
              </p>
            </div>

            <div className="field">
              <label htmlFor="identifier">Product identifier (EAN / barcode / SKU)</label>
              <input
                id="identifier"
                type="text"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                placeholder="8901234567890"
                autoComplete="off"
              />
              <p className="hint">
                Used to look up the seller listing and the registered official
                declaration. If either has no record, the case is routed to review —
                never assumed compliant.
              </p>
            </div>

            <div className="row">
              <div className="field" style={{ flex: '1 1 220px' }}>
                <label htmlFor="product">Product name (optional)</label>
                <input
                  id="product"
                  type="text"
                  value={productName}
                  onChange={(event) => setProductName(event.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="field" style={{ flex: '1 1 160px' }}>
                <label htmlFor="brand">Brand (optional)</label>
                <input
                  id="brand"
                  type="text"
                  value={brand}
                  onChange={(event) => setBrand(event.target.value)}
                  autoComplete="off"
                />
              </div>
            </div>

            <div className="row">
              <button className="btn" type="submit" disabled={busy}>
                {busy ? 'Verifying…' : 'Start verification'}
              </button>
              <span className="small muted">
                Extraction, source lookup and rule evaluation all run in one request.
              </span>
            </div>
          </form>
        </div>
      </div>

      {golden.length > 0 ? (
        <div className="panel">
          <div className="panel-h">
            <h2>Seeded demo cases</h2>
            <span className="spacer" />
            <span className="small muted">Deterministic · work with the network off</span>
          </div>
          <div className="panel-b">
            <div className="golden">
              {golden.map((item) => {
                const meta = classificationMeta(item.classification)
                return (
                  <button
                    key={item.case_id}
                    type="button"
                    onClick={() => navigate(`/case/${item.case_id}`)}
                  >
                    <span className={`badge b-${meta.tone === 'ok' ? 'pass' : meta.tone === 'bad' ? 'fail' : 'review'}`}>
                      <span className="glyph" aria-hidden="true">
                        {meta.glyph}
                      </span>
                      {meta.title}
                    </span>
                    <span>
                      <b>{item.case_id}</b>
                      <small>
                        {item.product_name || '—'} · {item.failed_rules} failed ·{' '}
                        {item.review_rules} for review
                      </small>
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
