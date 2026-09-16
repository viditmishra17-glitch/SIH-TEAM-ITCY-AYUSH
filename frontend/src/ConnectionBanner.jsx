import { useState } from 'react'
import { API_BASE, API_BASE_SOURCE, setApiBase } from './api.js'

// Shown only when the health check fails. A deployed frontend that cannot
// reach its backend is almost always a configuration problem, not a code
// problem, so this says which address was tried and where that address came
// from, and lets it be corrected without a rebuild or a dashboard.

const SOURCE_LABEL = {
  query: 'from the ?api= in this URL',
  saved: 'saved in this browser',
  'config.js': 'from config.js',
  build: 'baked in at build time (VITE_API_BASE_URL)',
  'same-origin': 'not configured - requests are going to this site itself',
}

export default function ConnectionBanner() {
  const [value, setValue] = useState(API_BASE)

  const submit = (event) => {
    event.preventDefault()
    setApiBase(value)
  }

  return (
    <div className="conn-banner" role="status">
      <div className="conn-head">
        <strong>Backend unreachable.</strong>{' '}
        <span>
          {API_BASE ? (
            <>
              Tried <code>{API_BASE}</code> ({SOURCE_LABEL[API_BASE_SOURCE]}).
            </>
          ) : (
            <>No backend address is configured, so requests are going to this
            site itself, which only serves files.</>
          )}
        </span>
      </div>

      <form className="conn-form" onSubmit={submit}>
        <label htmlFor="conn-url">Backend URL</label>

        <input
          id="conn-url"
          type="text"
          inputMode="url"
          spellCheck="false"
          placeholder="https://your-service.onrender.com"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />

        <button type="submit">Connect</button>
      </form>

      <p className="conn-hint">
        Saved in this browser and used on every reload. If the address is right
        and this persists, the backend is either asleep (a free Render service
        takes ~50s to wake) or is not allowing this site in
        TRIVERIFY_CORS_ORIGINS.
      </p>
    </div>
  )
}
