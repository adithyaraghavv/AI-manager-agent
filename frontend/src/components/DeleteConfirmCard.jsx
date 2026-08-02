import { useState } from 'react'

export default function DeleteConfirmCard({ proposal, onConfirm, onCancel }) {
  const [submitting, setSubmitting] = useState(false)

  async function handleConfirm() {
    if (submitting) return
    setSubmitting(true)
    await onConfirm(proposal.client_name)
    setSubmitting(false)
  }

  return (
    <div className="delete-card">
      <div className="delete-card__header">
        <span className="delete-card__icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 9v4m0 4h.01M10.29 3.86l-8.18 14.18A1.5 1.5 0 003.5 20h17a1.5 1.5 0 001.39-2.06L13.71 3.86a1.5 1.5 0 00-2.42 0z"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <div>
          <div className="delete-card__title">Delete {proposal.client_name}?</div>
          <p className="delete-card__body">
            This permanently removes their documents, database record, and files. This cannot be undone.
          </p>
        </div>
      </div>
      <div className="delete-card__stats">
        <span className="delete-card__chip">
          {proposal.phases_complete}/{proposal.total_phases} phases complete
        </span>
        <span className="delete-card__chip">
          {proposal.document_count} document{proposal.document_count === 1 ? '' : 's'} on file
        </span>
      </div>
      <div className="delete-card__actions">
        <button className="delete-card__confirm" onClick={handleConfirm} disabled={submitting}>
          {submitting ? 'Deleting…' : `Confirm & delete ${proposal.client_name}`}
        </button>
        <button className="delete-card__cancel" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
      </div>
    </div>
  )
}
