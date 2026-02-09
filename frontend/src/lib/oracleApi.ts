const rawOracleBase =
  import.meta.env.VITE_ORACLE_API_BASE_URL ??
  (import.meta.env.DEV ? "/oracle-api" : "");
const ORACLE_API_BASE = String(rawOracleBase).trim().replace(/\/+$/, "");

export function oracleApiUrl(path: string): string {
  if (!ORACLE_API_BASE) return path;
  return `${ORACLE_API_BASE}${path}`;
}

export async function oracleJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(oracleApiUrl(path), {
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
