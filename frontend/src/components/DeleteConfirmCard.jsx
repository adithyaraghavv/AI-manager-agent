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
      <div className="delete-card__warning">
        <span aria-hidden="true">⚠</span> This permanently deletes {proposal.client_name} — their documents,
        database record, and files. This cannot be undone.
      </div>
      <div className="delete-card__stats">
        {proposal.phases_complete}/{proposal.total_phases} phases complete · {proposal.document_count} document
        {proposal.document_count === 1 ? '' : 's'} on file
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
