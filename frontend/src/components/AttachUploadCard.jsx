import { useState } from 'react'
import DocTypeSelect from './DocTypeSelect'

export default function AttachUploadCard({ file, initialClientName, initialDocType, onConfirm, onCancel }) {
  const [clientName, setClientName] = useState(initialClientName || '')
  const [docType, setDocType] = useState(initialDocType || '')
  const [submitting, setSubmitting] = useState(false)

  async function handleConfirm() {
    if (!clientName.trim() || !docType.trim() || submitting) return
    setSubmitting(true)
    await onConfirm(clientName.trim(), docType.trim())
    setSubmitting(false)
  }

  return (
    <div className="upload-card">
      <div className="upload-card__file">📎 {file.name}</div>
      <div className="upload-card__row">
        <label>
          Client name
          <input
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
            placeholder="e.g. Hillenbrand"
            disabled={submitting}
          />
        </label>
        <label>
          Document type
          <DocTypeSelect value={docType} onChange={setDocType} disabled={submitting} />
        </label>
      </div>
      <div className="upload-card__actions">
        <button
          className="upload-card__confirm"
          onClick={handleConfirm}
          disabled={submitting || !clientName.trim() || !docType.trim()}
        >
          {submitting ? 'Uploading…' : 'Confirm & upload'}
        </button>
        <button className="upload-card__cancel" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
      </div>
    </div>
  )
}
