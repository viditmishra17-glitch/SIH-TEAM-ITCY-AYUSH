import { useEffect, useRef, useState } from 'react'
import { createCase, getCase, listCases } from '../api.js'
import { classificationMeta } from '../shared.js'

const MAX_FILE_BYTES = 12 * 1024 * 1024

const ALLOWED_TYPES = {
  'image/png': 'PNG',
  'image/jpeg': 'JPEG',
  'image/jpg': 'JPEG',
  'image/webp': 'WEBP',
  'image/bmp': 'BMP',
  'image/tiff': 'TIFF',
}

const DEMO_CASES = [
  'TV-0001',
  'TV-0002',
  'TV-0003',
  'TV-0004',
]

const DEMO_SAMPLE = {
  caseId: 'TV-0001',
  identifier: '8901234567890',
  productName: 'Sunrise Gold Chakki Atta',
  brand: 'Sunrise',
}

const VERIFY_STEPS = [
  {
    key: 'upload',
    label: 'Upload',
    detail: 'Reading the package photograph',
  },
  {
    key: 'extract',
    label: 'Extract',
    detail: 'Extracting label information',
  },
  {
    key: 'normalize',
    label: 'Normalize',
    detail: 'Standardizing extracted values',
  },
  {
    key: 'compare',
    label: 'Compare',
    detail: 'Comparing the three sources',
  },
  {
    key: 'classify',
    label: 'Classify',
    detail: 'Applying compliance rules',
  },
]

function getFileError(file) {
  if (!file) return null

  if (!ALLOWED_TYPES[file.type]) {
    return 'This file type is not supported. Please choose a PNG, JPEG, WEBP, BMP or TIFF image.'
  }

  if (file.size > MAX_FILE_BYTES) {
    return 'This image is larger than 12 MB. Please choose a smaller photograph.'
  }

  return null
}

function getIdentifierMessage(value) {
  const trimmed = value.trim()

  if (!trimmed) {
    return {
      type: 'error',
      text: 'Enter the product identifier before starting verification.',
    }
  }

  if (!/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(trimmed)) {
    return {
      type: 'error',
      text: 'Use only letters, numbers, dots, slashes, hyphens or underscores.',
    }
  }

  if (/^\d+$/.test(trimmed)) {
    if (![8, 12, 13, 14].includes(trimmed.length)) {
      return {
        type: 'warning',
        text: 'This looks like a numeric barcode, but its length is unusual. Please check it before verifying.',
      }
    }

    return {
      type: 'success',
      text: 'Looks like a valid numeric barcode.',
    }
  }

  return {
    type: 'info',
    text: 'Alphanumeric identifier detected — treating this as a SKU.',
  }
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function friendlySubmitError(error) {
  if (!error) {
    return 'Something went wrong while verifying this case. Please try again.'
  }

  if (error.userMessage) return error.userMessage

  if (error.status === 0) {
    return 'PARAKH could not reach the verification service. Make sure the backend is running and try again.'
  }

  if (error.status === 413) {
    return 'The photograph is too large. Please choose an image smaller than 12 MB.'
  }

  if (error.status === 415) {
    return 'This image format is not supported. Please use PNG, JPEG, WEBP, BMP or TIFF.'
  }

  if (error.status === 422) {
    return (
      error.message ||
      'The uploaded photograph could not be processed. Try a clearer package image.'
    )
  }

  if (error.status >= 500) {
    return 'The verification service encountered a problem while processing this case. Please try again.'
  }

  return (
    error.message ||
    'Verification could not be completed. Please check the details and try again.'
  )
}

export default function IntakePage({ navigate }) {
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [identifier, setIdentifier] = useState('')
  const [productName, setProductName] = useState('')
  const [brand, setBrand] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [golden, setGolden] = useState([])
  const [goldenError, setGoldenError] = useState(null)
  const [sampleBusy, setSampleBusy] = useState(false)
  const [progressStep, setProgressStep] = useState(-1)

  const inputRef = useRef(null)
  const progressTimerRef = useRef(null)
  const previewRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    listCases()
      .then((data) => {
        if (cancelled) return

        setGolden((data.items || []).filter((item) => item.is_golden))
        setGoldenError(null)
      })
      .catch((err) => {
        if (cancelled) return

        setGolden([])
        setGoldenError(
          err.userMessage ||
          'The demo cases could not be loaded. You can still upload your own package photograph.',
        )
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    return () => {
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current)
      }

      if (previewRef.current) {
        URL.revokeObjectURL(previewRef.current)
      }
    }
  }, [])

  const setSelectedFile = (nextFile) => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current)
      previewRef.current = null
    }

    setFile(null)
    setPreviewUrl(null)
    setError(null)

    if (!nextFile) return

    const fileError = getFileError(nextFile)

    if (fileError) {
      setError(fileError)

      if (inputRef.current) {
        inputRef.current.value = ''
      }

      return
    }

    const url = URL.createObjectURL(nextFile)
    previewRef.current = url

    setFile(nextFile)
    setPreviewUrl(url)
  }

  const onFileChange = (event) => {
    setSelectedFile(event.target.files?.[0] || null)
  }

  const clearFile = () => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current)
      previewRef.current = null
    }

    setFile(null)
    setPreviewUrl(null)

    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  /*
   * Load a deterministic demo image and populate its metadata.
   *
   * Product metadata comes from /cases because the list endpoint exposes
   * product_name, brand and identifier directly. The image itself comes
   * from the full case endpoint.
   */
  const loadSample = async () => {
    setSampleBusy(true)
    setError(null)

    try {
      const caseId = DEMO_SAMPLE.caseId

      // Get the complete seeded case so the image always comes
      // from the backend's actual stored demo data.
      const sampleCase = await getCase(caseId)

      const image =
        (sampleCase.images || []).find(
          (item) => item.kind === 'ORIGINAL',
        ) || sampleCase.images?.[0]

      if (!image?.url) {
        throw new Error(
          'The sample case does not contain a package photograph.',
        )
      }

      const response = await fetch(image.url)

      if (!response.ok) {
        throw new Error(
          'The sample package photograph could not be loaded.',
        )
      }

      const blob = await response.blob()

      const sampleFile = new File(
        [blob],
        `${caseId.toLowerCase()}-sample.png`,
        {
          type: blob.type || 'image/png',
        },
      )

      // Set the image.
      setSelectedFile(sampleFile)

      // TV-0001 is a deterministic seeded demo case.
      // Populate the known demo metadata directly so the
      // "Try a sample image" experience never depends on
      // another API response for form values.
      setIdentifier(DEMO_SAMPLE.identifier)
      setProductName(DEMO_SAMPLE.productName)
      setBrand(DEMO_SAMPLE.brand)
    } catch (err) {
      setError(
        err.userMessage ||
        err.message ||
        'The sample case could not be loaded. Please try again.',
      )
    } finally {
      setSampleBusy(false)
    }
  }

  const onSubmit = async (event) => {
    event.preventDefault()

    setError(null)

    if (!file) {
      setError(
        'Select a package photograph first, or use the sample image button.',
      )
      return
    }

    const identifierState = getIdentifierMessage(identifier)

    if (identifierState.type === 'error') {
      setError(identifierState.text)
      return
    }

    setBusy(true)
    setProgressStep(0)

    let step = 0

    progressTimerRef.current = setInterval(() => {
      step += 1

      if (step < VERIFY_STEPS.length) {
        setProgressStep(step)
      }
    }, 850)

    try {
      const created = await createCase({
        file,
        identifier: identifier.trim(),
        productName: productName.trim(),
        brand: brand.trim(),
      })

      setProgressStep(VERIFY_STEPS.length - 1)

      navigate(`/case/${created.case_id}`)
    } catch (err) {
      setError(friendlySubmitError(err))
    } finally {
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current)
        progressTimerRef.current = null
      }

      setBusy(false)
      setProgressStep(-1)
    }
  }

  const identifierState = identifier.trim()
    ? getIdentifierMessage(identifier)
    : null

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-h">
          <div>
            <h2>New verification case</h2>

            <p className="panel-subtitle">
              Upload a package photograph and verify its Legal Metrology
              declarations.
            </p>
          </div>
        </div>

        <div className="panel-b">
          {error ? <div className="alert error">{error}</div> : null}

          <form className="form" onSubmit={onSubmit}>
            <div className="field">
              <div className="field-label-row">
                <label htmlFor="image">Package photograph</label>

                <span className="small muted">Max 12 MB</span>
              </div>

              {!file ? (
                <button
                  type="button"
                  className="upload-box"
                  onClick={() => inputRef.current?.click()}
                  disabled={busy || sampleBusy}
                >
                  <span className="upload-icon" aria-hidden="true">
                    ↑
                  </span>

                  <span>
                    <b>Choose a package photograph</b>
                    <small>
                      PNG, JPEG, WEBP, BMP or TIFF
                    </small>
                  </span>
                </button>
              ) : (
                <div className="selected-file">
                  <div className="image-preview">
                    <img
                      src={previewUrl}
                      alt="Selected package preview"
                    />
                  </div>

                  <div className="selected-file-info">
                    <b>{file.name}</b>

                    <span>
                      {ALLOWED_TYPES[file.type] || 'Image'} ·{' '}
                      {formatBytes(file.size)}
                    </span>

                    <span className="file-valid">
                      ✓ Image ready for verification
                    </span>
                  </div>

                  <button
                    type="button"
                    className="btn ghost sm"
                    onClick={clearFile}
                    disabled={busy || sampleBusy}
                  >
                    Change
                  </button>
                </div>
              )}

              <input
                ref={inputRef}
                id="image"
                className="sr-only"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff"
                onChange={onFileChange}
                disabled={busy || sampleBusy}
              />

              <div className="sample-row">
                <button
                  type="button"
                  className="btn ghost sample-btn"
                  onClick={loadSample}
                  disabled={busy || sampleBusy}
                >
                  {sampleBusy
                    ? 'Loading sample…'
                    : 'Try a sample image'}
                </button>

                <span className="small muted">
                  Uses a deterministic offline demo case.
                </span>
              </div>

              <p className="hint">
                Use a clear photograph of the package label. The original
                image is preserved and the verification pipeline extracts
                the visible declarations.
              </p>
            </div>

            <div className="field">
              <div className="field-label-row">
                <label htmlFor="identifier">
                  Product identifier (EAN / barcode / SKU)
                </label>

                {identifierState ? (
                  <span
                    className={`identifier-state ${identifierState.type}`}
                  >
                    {identifierState.type === 'success'
                      ? 'Valid barcode'
                      : identifierState.type === 'warning'
                        ? 'Check barcode'
                        : 'SKU'}
                  </span>
                ) : null}
              </div>

              <input
                id="identifier"
                type="text"
                value={identifier}
                onChange={(event) =>
                  setIdentifier(event.target.value)
                }
                placeholder="e.g. 8901234567890"
                autoComplete="off"
                aria-invalid={
                  identifierState?.type === 'error'
                }
                disabled={busy}
              />

              {identifierState ? (
                <p
                  className={`inline-validation ${identifierState.type}`}
                >
                  {identifierState.text}
                </p>
              ) : (
                <p className="hint">
                  Enter the identifier printed on the package. Numeric
                  EAN/barcodes are preferred; alphanumeric values are
                  treated as SKUs.
                </p>
              )}
            </div>

            <div className="row">
              <div
                className="field"
                style={{ flex: '1 1 220px' }}
              >
                <label htmlFor="product">
                  Product name (optional)
                </label>

                <input
                  id="product"
                  type="text"
                  value={productName}
                  onChange={(event) =>
                    setProductName(event.target.value)
                  }
                  autoComplete="off"
                  disabled={busy}
                />
              </div>

              <div
                className="field"
                style={{ flex: '1 1 160px' }}
              >
                <label htmlFor="brand">
                  Brand (optional)
                </label>

                <input
                  id="brand"
                  type="text"
                  value={brand}
                  onChange={(event) =>
                    setBrand(event.target.value)
                  }
                  autoComplete="off"
                  disabled={busy}
                />
              </div>
            </div>

            {busy ? (
              <div
                className="verification-progress"
                aria-live="polite"
              >
                <div className="progress-heading">
                  <div>
                    <b>Verification in progress</b>

                    <span>
                      {VERIFY_STEPS[progressStep]?.detail ||
                        'Processing the case…'}
                    </span>
                  </div>

                  <strong>
                    {Math.round(
                      ((progressStep + 1) /
                        VERIFY_STEPS.length) *
                      100,
                    )}
                    %
                  </strong>
                </div>

                <div className="progress-track">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${((progressStep + 1) /
                        VERIFY_STEPS.length) *
                        100
                        }%`,
                    }}
                  />
                </div>

                <div className="progress-steps">
                  {VERIFY_STEPS.map((stepItem, index) => {
                    const completed = index < progressStep
                    const active = index === progressStep

                    return (
                      <div
                        key={stepItem.key}
                        className={`progress-step ${completed ? 'completed' : ''
                          } ${active ? 'active' : ''}`}
                      >
                        <span>
                          {completed
                            ? '✓'
                            : active
                              ? '•'
                              : index + 1}
                        </span>

                        {stepItem.label}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <div className="submit-row">
                <button
                  className="btn"
                  type="submit"
                  disabled={
                    !file ||
                    !identifier.trim() ||
                    identifierState?.type === 'error'
                  }
                >
                  Start verification
                </button>

                <span className="small muted">
                  The package, seller listing and official record are
                  checked together.
                </span>
              </div>
            )}
          </form>
        </div>
      </div>

      {goldenError ? (
        <div className="alert info">
          <b>Demo cases unavailable.</b> {goldenError}
        </div>
      ) : null}

      {golden.length > 0 ? (
        <div className="panel">
          <div className="panel-h">
            <div>
              <h2>Seeded demo cases</h2>

              <p className="panel-subtitle">
                Open a deterministic result without running a new
                verification.
              </p>
            </div>

            <span className="spacer" />

            <span className="small muted">
              Works offline
            </span>
          </div>

          <div className="panel-b">
            <div className="golden">
              {golden.map((item) => {
                const meta = classificationMeta(
                  item.classification,
                )

                return (
                  <button
                    key={item.case_id}
                    type="button"
                    onClick={() =>
                      navigate(`/case/${item.case_id}`)
                    }
                  >
                    <span
                      className={`badge ${meta.tone === 'ok'
                        ? 'b-pass'
                        : meta.tone === 'bad'
                          ? 'b-fail'
                          : 'b-review'
                        }`}
                    >
                      <span
                        className="glyph"
                        aria-hidden="true"
                      >
                        {meta.glyph}
                      </span>

                      {meta.title}
                    </span>

                    <span>
                      <b>{item.case_id}</b>

                      <small>
                        {item.product_name || '—'} ·{' '}
                        {item.failed_rules} failed ·{' '}
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