export type User = { username: string; role: string; organization_id: string }
export type Citation = { citation_id: string; title: string; section: string; effective_from: string; effective_to: string | null; source_url: string | null; fragment: string }
export type Consultation = { id: string; question: string; target_date: string; status: 'ai_draft' | 'insufficient_evidence'; answer: string | null; citations: Citation[] }
export type Obligation = { id: string; title: string; description: string; due_date: string; status: string; priority: string; deadline_state: string; days_remaining: number }
export type Prescription = { id: string; title: string; content: string }
export type Draft = { id: string; prescription_id: string; content: string; status: string; citations: Citation[] }
export type Attachment = { id: string; filename: string; mime_type: string; status: string }
export type Source = { id: string; title: string; section: string; effective_from: string; effective_to: string | null; source_url: string | null }
export type Job = { id: string; status: string; result: { due: { id: string; title: string; days_remaining: number }[] } | null; error: string | null }

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

export async function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(`/api/v1${path}`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body })
  if (!response.ok) {
    let message = `Ошибка ${response.status}`
    try { const error = await response.json(); message = error.message || message } catch { /* use status */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
