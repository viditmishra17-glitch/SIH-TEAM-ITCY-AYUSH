import { useCallback, useEffect, useState } from 'react'
import { getCase, reverifyCase } from '../api.js'
import VerdictPanel from '../components/VerdictPanel.jsx'
import LabelViewer from '../components/LabelViewer.jsx'
import ComparisonTable from '../components/ComparisonTable.jsx'
import FindingsPanel from '../components/FindingsPanel.jsx'
import EvidenceDrawer from '../components/EvidenceDrawer.jsx'

export default function CasePage({ caseId }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [activeField, setActiveField] = useState(null)
  const [evidenceId, setEvidenceId] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getCase(caseId)
      .then((data) => setResult(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [caseId])

  useEffect(() => {
    setActiveField(null)
    setEvidenceId(null)
    load()
  }, [load])

  const onReverify = useCallback(() => {
    setBusy(true)
    reverifyCase(caseId)
      .then((data) => setResult(data))
      .catch((err) => setError(err.message))
      .finally(() => setBusy(false))
  }, [caseId])

  if (loading) return <p className="center">Loading case {caseId}…</p>
  if (error) {
    return (
      <div className="alert error">
        {error}{' '}
        <button type="button" className="btn ghost sm" onClick={load}>
          Retry
        </button>
      </div>
    )
  }
  if (!result) return null

  return (
    <>
      <VerdictPanel result={result} onReverify={onReverify} busy={busy} />

      <div className="workspace">
        <LabelViewer
          result={result}
          activeField={activeField}
          onSelectField={(name) => setActiveField((prev) => (prev === name ? null : name))}
        />
        <ComparisonTable
          result={result}
          activeField={activeField}
          onSelectField={setActiveField}
          onOpenEvidence={setEvidenceId}
        />
        <FindingsPanel
          result={result}
          activeField={activeField}
          onSelectField={setActiveField}
          onOpenEvidence={setEvidenceId}
        />
      </div>

      {evidenceId ? (
        <EvidenceDrawer
          caseId={caseId}
          evidenceId={evidenceId}
          onClose={() => setEvidenceId(null)}
        />
      ) : null}
    </>
  )
}
