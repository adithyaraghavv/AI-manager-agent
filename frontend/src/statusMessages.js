// Templated conversational sentences that accompany every red/green status
// card (upload, delete) shown in the chat. The colored card stays for a
// quick at-a-glance signal; these are the follow-up chat bubble explaining
// what happened, why, and what to do next — so the upload/delete flow reads
// like part of the conversation instead of a bare system notification.
//
// Templated rather than a live LLM call: the wording is fixed per outcome
// (there's no ambiguity to reason about — a mismatch is a mismatch), so a
// canned sentence is faster, free, and never drifts or hallucinates.

export function uploadSuccessMessage(result) {
  const versionNote =
    result.version_number > 1
      ? ` Earlier versions are kept, not overwritten, so nothing was lost.`
      : "";
  return (
    `Your document has been successfully uploaded and filed under the "${result.phase}" phase.\n\n` +
    `It's stored as version ${result.version_number} and is ready for retrieval and future updates.${versionNote}`
  );
}

export function uploadErrorMessage(err) {
  const code = err?.code;
  const detail = err?.detail;

  if (code === "type_mismatch") {
    const docType = detail?.doc_type;
    return (
      `I couldn't upload the document because the uploaded file appears to be different from ` +
      `the document type you selected.\n\n` +
      (docType
        ? `For example, if "${docType}" is selected, the uploaded file should also be a "${docType}" document.\n\n`
        : "") +
      `Please verify the document type and upload the correct file. Once the document and selected ` +
      `type match, the upload can proceed successfully.`
    );
  }

  if (code === "type_uncertain") {
    return (
      `I wasn't able to confidently confirm this file matches the document type you selected.\n\n` +
      `To be safe, I didn't file it — please double check it's the right document and try uploading again.`
    );
  }

  if (code === "validation_failed") {
    return (
      `I couldn't complete the document type check for this upload, so I didn't file it rather than ` +
      `risk misclassifying it.\n\n` +
      `Please review the file and try again in a moment.`
    );
  }

  if (code === "unknown_doc_type") {
    return `I couldn't recognize that document type. Please pick a valid document type and try again.`;
  }

  if (code === "gating_blocked") {
    const missing = detail?.missing_documents || [];
    const phase = detail?.blocking_phase;
    const bulletList = missing.map((doc) => `• ${doc}`).join("\n");
    return (
      `I found that some required documents are still missing before the "${phase}" phase can be ` +
      `completed.\n\n` +
      (bulletList ? `The following documents need to be uploaded:\n${bulletList}\n\n` : "") +
      `Once these are uploaded, the phase requirements will be satisfied. If you need any of these ` +
      `templates, I can retrieve them directly — just ask.`
    );
  }

  if (code === "invalid_upload") {
    return (
      `I couldn't complete the upload because ${(detail?.message || err.message || "").toLowerCase()}\n\n` +
      `Please check the file and try again.`
    );
  }

  if (code === "version_conflict") {
    return `That upload collided with another one landing at the same moment. Please try uploading again.`;
  }

  return `I couldn't complete the upload — ${err?.message || "something went wrong"}. Please try again.`;
}

export function deleteSuccessMessage(clientName) {
  return (
    `I've removed ${clientName} from the active client list.\n\n` +
    `Their records and files are kept for a short recovery window in case this needs to be undone, ` +
    `but they won't show up anywhere going forward.`
  );
}

export function deleteCancelledMessage(clientName) {
  return `No changes made — ${clientName} wasn't deleted.`;
}

export function deleteErrorMessage(clientName, err) {
  return (
    `I couldn't remove ${clientName} — ${err?.message || "something went wrong"}.\n\n` +
    `Feel free to try again.`
  );
}
