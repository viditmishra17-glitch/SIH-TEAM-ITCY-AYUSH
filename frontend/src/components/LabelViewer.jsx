import { useMemo } from 'react'
import { apiUrl } from '../api.js'

/**
 * Left pane: the product image with clickable OCR regions.
 *
 * Bounding boxes arrive in ORIGINAL image pixel coordinates, so they are
 * converted to percentages of the rendered image. That keeps the overlay
 * aligned at every width without measuring the DOM.
 */
export default function LabelViewer({ result, activeField, onSelectField }) {
  const image = useMemo(
    () => result.images.find((img) => img.kind === 'ORIGINAL') || result.images[0],
    [result.images],
  )

  const hotspots = useMemo(() => {
    if (!image || !image.width || !image.height) return []
    return result.field_order
      .map((name) => {
        const field = result.fields[name]
        const box = field?.photo?.bbox
        if (!box || box.length < 4) return null
        return {
          name,
          label: field.label,
          status: field.status,
          display: field.photo.display || field.photo.raw || '',
          style: {
            left: `${(box[0] / image.width) * 100}%`,
            top: `${(box[1] / image.height) * 100}%`,
            width: `${(box[2] / image.width) * 100}%`,
            height: `${(box[3] / image.height) * 100}%`,
          },
        }
      })
      .filter(Boolean)
  }, [result, image])

  if (!image) {
    return (
      <div className="panel">
        <div className="panel-h">
          <h2>Physical label</h2>
        </div>
        <div className="panel-b center">No image stored for this case.</div>
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="panel-h">
        <h2>Physical label</h2>
        <span className="spacer" />
        <a
          className="small"
          href={apiUrl(image.url)}
          target="_blank"
          rel="noreferrer"
          title="Open the original photograph at full size"
        >
          Full size ↗
        </a>
      </div>
      <div className="panel-b">
        <div className="label-wrap">
          <img
            src={apiUrl(image.url)}
            alt={`Uploaded packaged commodity label for case ${result.case_id}`}
          />
          {hotspots.map((spot) => (
            <button
              key={spot.name}
              type="button"
              className={[
                'hotspot',
                activeField === spot.name ? 'is-active' : '',
                spot.status === 'MISMATCH' ? 'is-mismatch' : '',
              ]
                .join(' ')
                .trim()}
              style={spot.style}
              onClick={() => onSelectField(spot.name)}
              title={`${spot.label}: ${spot.display}`}
              aria-label={`Highlight ${spot.label}, read as ${spot.display}`}
              aria-pressed={activeField === spot.name}
            />
          ))}
        </div>
        <p className="viewer-note">
          {hotspots.length} extracted region{hotspots.length === 1 ? '' : 's'}. Click a
          highlight, or a row in the comparison table, to link the two. Quality score{' '}
          {image.quality_score ?? '—'} · {image.width}×{image.height} px.
        </p>
      </div>
    </div>
  )
}
