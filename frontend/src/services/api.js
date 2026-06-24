// services/api.js
// Centralized API client for the PM Document Assistant backend

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

// ─────────────────────────────────────────────
// Core fetch wrapper with error handling
// ─────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ─────────────────────────────────────────────
// Chat API
// ─────────────────────────────────────────────
export async function sendMessage(message, conversationHistory = [], sessionId = null) {
  return apiFetch("/chat/", {
    method: "POST",
    body: JSON.stringify({
      message,
      conversation_history: conversationHistory,
      session_id: sessionId,
    }),
  });
}

// ─────────────────────────────────────────────
// Templates API
// ─────────────────────────────────────────────
export async function getTemplates() {
  return apiFetch("/templates/");
}

export async function getTemplate(docType) {
  return apiFetch(`/templates/${docType}`);
}

export function getTemplateDownloadUrl(filename) {
  return `${BASE_URL}/templates/download/${filename}`;
}

// ─────────────────────────────────────────────
// Upload API
// ─────────────────────────────────────────────
export async function uploadDocument(file, clientName, documentType, notes = "") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("client_name", clientName);
  formData.append("document_type", documentType);
  formData.append("notes", notes);

  const res = await fetch(`${BASE_URL}/upload/`, {
    method: "POST",
    body: formData, // Don't set Content-Type — browser sets multipart boundary
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: HTTP ${res.status}`);
  }
  return res.json();
}

export async function detectDocumentType(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE_URL}/upload/detect-type`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) return null;
  return res.json();
}

// ─────────────────────────────────────────────
// Documents API
// ─────────────────────────────────────────────
export async function getDocuments(clientFilter = null) {
  const qs = clientFilter ? `?client=${encodeURIComponent(clientFilter)}` : "";
  return apiFetch(`/documents/${qs}`);
}

export async function getClients() {
  return apiFetch("/documents/clients");
}

export async function searchDocuments(query) {
  return apiFetch(`/documents/search?q=${encodeURIComponent(query)}`);
}
