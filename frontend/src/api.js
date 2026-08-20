const BASE = "/api";

/**
 * Parse res.body as JSON. Throw with a caller-supplied label if:
 * - the response is non-OK and the body has no JSON `.detail`
 * - the response is OK but the body isn't valid JSON (proxy HTML error page, etc.)
 *
 * Server errors (500s, proxy errors) aren't always JSON — surface the raw text
 * instead of failing again on JSON.parse and hiding the real error message.
 */
async function parseJsonOrRaise(res, label) {
  const raw = await res.text();
  let data;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    if (!res.ok)
      throw new Error(
        `${label} failed (${res.status}): ${raw || "no response body"}`,
      );
    throw new Error(
      `${label} succeeded but response was not valid JSON: ${raw}`,
    );
  }
  if (!res.ok) {
    throw new Error(data?.detail || `${label} failed (${res.status})`);
  }
  return data;
}

export async function sendChat(messages) {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Chat request failed (${res.status}): ${body}`);
  }
  return res.json();
}

export async function uploadDocument(
  clientName,
  docType,
  file,
  uploadedBy,
  comment,
) {
  const form = new FormData();
  form.append("doc_type", docType);
  form.append("file", file);
  if (uploadedBy) form.append("uploaded_by", uploadedBy);
  if (comment) form.append("comment", comment);

  const res = await fetch(
    `${BASE}/clients/${encodeURIComponent(clientName)}/documents`,
    {
      method: "POST",
      body: form,
    },
  );

  return parseJsonOrRaise(res, "Upload");
}

export async function getPhases() {
  const res = await fetch(`${BASE}/phases`);
  if (!res.ok) throw new Error(`Failed to load phases (${res.status})`);
  const body = await res.json();
  return body.phases;
}

export async function searchDocuments(query) {
  const res = await fetch(
    `${BASE}/documents/search?q=${encodeURIComponent(query)}`,
  );
  if (!res.ok) throw new Error(`Search failed (${res.status})`);
  const body = await res.json();
  return body.results;
}

export async function getClientStatuses() {
  const res = await fetch(`${BASE}/clients/status`);
  if (!res.ok)
    throw new Error(`Failed to load client statuses (${res.status})`);
  const body = await res.json();
  return body.clients;
}

export async function deleteClient(clientName) {
  const res = await fetch(`${BASE}/clients/${encodeURIComponent(clientName)}`, {
    method: "DELETE",
  });
  return parseJsonOrRaise(res, "Delete");
}

export function templateDownloadUrl(docType, clientName) {
  return `${BASE}/templates/${encodeURIComponent(docType)}/download?client_name=${encodeURIComponent(clientName)}`;
}

export async function getDocumentVersions(clientName, docType) {
  const res = await fetch(
    `${BASE}/clients/${encodeURIComponent(clientName)}/documents/${encodeURIComponent(docType)}/versions`,
  );
  if (!res.ok)
    throw new Error(`Failed to load version history (${res.status})`);
  const body = await res.json();
  return body.versions;
}

export async function restoreDocumentVersion(
  clientName,
  docType,
  versionNumber,
  uploadedBy,
) {
  const form = new FormData();
  if (uploadedBy) form.append("uploaded_by", uploadedBy);

  const res = await fetch(
    `${BASE}/clients/${encodeURIComponent(clientName)}/documents/${encodeURIComponent(docType)}/versions/${versionNumber}/restore`,
    { method: "POST", body: form },
  );
  return parseJsonOrRaise(res, "Restore");
}

export async function checkHealth() {
  try {
    const res = await fetch("/health");
    return res.ok;
  } catch {
    return false;
  }
}
