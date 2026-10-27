export async function readApiResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  let payload: unknown;
  try {
    payload = raw ? JSON.parse(raw) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail;
    throw new Error(typeof detail === "string" ? detail : raw.trim() || response.statusText || `HTTP ${response.status}`);
  }
  if (payload === null) throw new Error("Сервер вернул ответ без JSON");
  return payload as T;
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  headers.set("X-Requested-With", "DreamTeam");
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  if (response.status === 401) window.dispatchEvent(new Event("session-expired"));
  return readApiResponse<T>(response);
}

export function post<T>(path: string, payload?: unknown) {
  return request<T>(path, { method: "POST", body: payload === undefined ? undefined : JSON.stringify(payload) });
}

export function put<T>(path: string, payload: unknown) {
  return request<T>(path, { method: "PUT", body: JSON.stringify(payload) });
}

export async function download(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  headers.set("X-Requested-With", "DreamTeam");
  const response = await fetch(path, { headers, cache: "no-store" });
  if (!response.ok) {
    let detail = "Не удалось скачать файл";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch { /* keep generic message */ }
    throw new Error(detail);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
