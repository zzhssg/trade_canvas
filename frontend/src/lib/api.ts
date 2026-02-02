const rawBase = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "");
const API_BASE = String(rawBase).trim().replace(/\/+$/, "");

export function apiUrl(path: string) {
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

export function apiHttpBase(): string {
  if (API_BASE) return API_BASE;
  return window.location.origin.replace(/\/+$/, "");
}

export function apiWsBase(): string {
  const httpBase = apiHttpBase();
  if (httpBase.startsWith("https://")) return `wss://${httpBase.slice("https://".length)}`;
  if (httpBase.startsWith("http://")) return `ws://${httpBase.slice("http://".length)}`;
  return httpBase;
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }

  return (await res.json()) as T;
}
