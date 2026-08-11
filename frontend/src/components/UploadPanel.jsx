import { useState } from 'react'
import { uploadDocument } from '../api'
import DocTypeSelect from './DocTypeSelect'

export default function UploadPanel() {
  const [clientName, setClientName] = useState('')
  const [docType, setDocType] = useState('')
  const [file, setFile] = useState(null)
  const [uploadedBy, setUploadedBy] = useState('')
  const [comment, setComment] = useState('')
  const [status, setStatus] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!clientName || !docType || !file) return

    setSubmitting(true)
    setStatus(null)
    try {
      const result = await uploadDocument(clientName, docType, file, uploadedBy, comment)
      setStatus({
        ok: true,
        message: `Filed under "${result.phase}" as version ${result.version_number} (${result.filename})`,
      })
      // Clear doc type + file (each upload needs a fresh pick), but keep the client name —
      // uploading several documents for the same client back-to-back is the common case.
      setDocType('')
      setFile(null)
      setComment('')
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
          <DocTypeSelect value={docType} onChange={setDocType} />
        </label>
        <label>
          File
          <input type="file" onChange={(e) => setFile(e.target.files[0] ?? null)} />
        </label>
        <label>
          Uploaded by <span className="upload-panel__optional">(optional)</span>
          <input value={uploadedBy} onChange={(e) => setUploadedBy(e.target.value)} placeholder="Your name" />
        </label>
        <label>
          What changed <span className="upload-panel__optional">(optional)</span>
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="e.g. Updated architecture diagram"
          />
        </label>
        <button type="submit" disabled={submitting || !clientName || !docType || !file}>
          {submitting ? 'Uploading…' : 'Upload'}
        </button>
      </form>
      {status && <div className={`upload-panel__status upload-panel__status--${status.ok ? 'ok' : 'error'}`}>{status.message}</div>}
    </div>
  )
}
