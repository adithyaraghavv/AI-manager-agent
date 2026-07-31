const BASE = '/api'

export async function sendChat(messages) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Chat request failed (${res.status}): ${body}`)
  }
  return res.json()
}

export async function uploadDocument(clientName, docType, file) {
  const form = new FormData()
  form.append('doc_type', docType)
  form.append('file', file)

  const res = await fetch(`${BASE}/clients/${encodeURIComponent(clientName)}/documents`, {
    method: 'POST',
    body: form,
  })

  const raw = await res.text()
  let body
  try {
    body = JSON.parse(raw)
  } catch {
    // Server errors (500s, proxy errors) aren't always JSON — surface the raw text
    // instead of failing again on JSON.parse and hiding the real error message.
    if (!res.ok) throw new Error(`Upload failed (${res.status}): ${raw || 'no response body'}`)
    throw new Error(`Upload succeeded but response was not valid JSON: ${raw}`)
  }

  if (!res.ok) {
    throw new Error(body.detail || `Upload failed (${res.status})`)
  }
  return body
}

export function templateDownloadUrl(docType, clientName) {
  return `${BASE}/templates/${encodeURIComponent(docType)}/download?client_name=${encodeURIComponent(clientName)}`
}

export async function checkHealth() {
  try {
    const res = await fetch('/health')
    return res.ok
  } catch {
    return false
  }
}
