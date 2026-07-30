import { useState } from 'react'
import { uploadDocument } from '../api'

export default function UploadPanel() {
  const [clientName, setClientName] = useState('')
  const [docType, setDocType] = useState('')
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!clientName || !docType || !file) return

    setSubmitting(true)
    setStatus(null)
    try {
      const result = await uploadDocument(clientName, docType, file)
      setStatus({ ok: true, message: `Filed under "${result.phase}" as ${result.filename}` })
      setFile(null)
      e.target.reset()
    } catch (err) {
      setStatus({ ok: false, message: err.message })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="upload-panel">
      <h2>File a completed document</h2>
      <p className="upload-panel__hint">
        Filled in a template outside the tool? Upload it here. Blocked if required documents from
        any earlier phase are missing for this client.
      </p>
      <form onSubmit={handleSubmit}>
        <label>
          Client name
          <input value={clientName} onChange={(e) => setClientName(e.target.value)} placeholder="e.g. Hillenbrand" />
        </label>
        <label>
          Document type
          <input value={docType} onChange={(e) => setDocType(e.target.value)} placeholder="e.g. Pricing, Approved HLD" />
        </label>
        <label>
          File
          <input type="file" onChange={(e) => setFile(e.target.files[0] ?? null)} />
        </label>
        <button type="submit" disabled={submitting || !clientName || !docType || !file}>
          {submitting ? 'Uploading…' : 'Upload'}
        </button>
      </form>
      {status && <div className={`upload-panel__status upload-panel__status--${status.ok ? 'ok' : 'error'}`}>{status.message}</div>}
    </div>
  )
}
