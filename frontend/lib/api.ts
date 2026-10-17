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
  const key = sessionStorage.getItem("appKey");
  if (key) headers.set("X-API-Key", key);
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  if (response.status === 401) {
    const entered = window.prompt("Введите ключ доступа к приложению");
    if (entered) {
      sessionStorage.setItem("appKey", entered);
      return request<T>(path, options);
    }
  }
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
  const key = sessionStorage.getItem("appKey");
  if (key) headers.set("X-API-Key", key);
  const response = await fetch(path, { headers });
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
