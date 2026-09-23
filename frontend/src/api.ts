export type User = { username: string; role: string; organization_id: string }
export type Citation = {
  citation_id?: string; document_category?: 'normative' | 'obligation'; title: string;
  section?: string; effective_from?: string | null; effective_to?: string | null;
  date_provenance?: string; source_url?: string | null; original_url?: string;
  fragment: string; revision_id?: string
}
export type Consultation = { id: string; question: string; target_date: string; status: 'ai_draft' | 'demo_unverified' | 'insufficient_evidence'; answer: string | null; citations: Citation[] }
export type DocumentSummary = {
  document_id: string; revision_id: string; document_category: 'normative' | 'obligation';
  title: string; filename: string; status: string; date_provenance: string;
  valid_from: string | null; valid_to: string | null; due_date: string | null;
  source_fragment: string | null; original_url: string; source_url: string | null
}
export type DocumentJob = { id: string; revision_id: string; status: string; stage: string; error_code: string | null; error_message: string | null }
export type DashboardItem = DocumentSummary & { days_remaining: number; sla_state: string; reminder: string | null; escalated_at: string | null; escalated_to: string | null }
export type Draft = { id: string; prescription_id: string | null; obligation_revision_id: string | null; template_id: string | null; content: string; status: string; citations: Citation[] }
export type Escalation = { id: string; revision_id: string; title: string; created_at: string }

let token = sessionStorage.getItem('token') || ''
export function setToken(value: string) { token = value; if (value) sessionStorage.setItem('token', value); else sessionStorage.removeItem('token') }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  })
  if (!response.ok) {
    let message = `Ошибка ${response.status}`
    try { const body = await response.json(); message = body.message || message } catch { /* use status */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export function post<T>(path: string, body?: unknown) { return api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }) }
export function patch<T>(path: string, body: unknown) { return api<T>(path, { method: 'PATCH', body: JSON.stringify(body) }) }

export async function uploadDocument(category: 'normative' | 'obligation', title: string, file: File) {
  const body = new FormData()
  body.append('document_category', category)
  body.append('title', title)
  body.append('file', file)
  const response = await fetch('/api/v1/documents', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body })
  if (!response.ok) {
    let message = `Ошибка ${response.status}`
    try { const error = await response.json(); message = error.message || message } catch { /* use status */ }
    throw new Error(message)
  }
  return response.json() as Promise<{ job_id: string; revision_id: string; document_id: string; status: string }>
}

export async function downloadOriginal(revisionId: string) {
  const response = await fetch(`/api/v1/documents/${revisionId}/original`, { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) throw new Error(`Не удалось скачать оригинал: ${response.status}`)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = `${revisionId}.docx`
    link.click()
  } finally { setTimeout(() => URL.revokeObjectURL(url), 1000) }
}
