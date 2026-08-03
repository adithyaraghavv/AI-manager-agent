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
      <div className="upload-card__header">
        <span className="upload-card__icon" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path
              d="M20.5 12.5L12.83 20.17a5 5 0 01-7.07-7.07L13.83 5a3.5 3.5 0 014.95 4.95l-7.78 7.78a2 2 0 01-2.83-2.83l7.07-7.07"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <div>
          <div className="upload-card__file">{file.name}</div>
          <div className="upload-card__subtitle">Confirm the details below before filing this document</div>
        </div>
      </div>
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
