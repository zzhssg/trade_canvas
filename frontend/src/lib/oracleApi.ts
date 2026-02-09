const rawOracleBase = import.meta.env.VITE_ORACLE_API_BASE_URL ?? (import.meta.env.DEV ? "/oracle-api" : "");
const ORACLE_API_BASE = String(rawOracleBase).trim().replace(/\/+$/, "");

export function oracleApiUrl(path: string): string {
  if (!ORACLE_API_BASE) return path;
  return `${ORACLE_API_BASE}${path}`;
}

function simplifyErrorMessage(text: string, status: number): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return `HTTP ${status}`;
  }

  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    // fall through
  }

  return trimmed;
}

export async function oracleJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(oracleApiUrl(path), {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(init?.headers ?? {})
      }
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`oracle_api_unreachable: 请先启动 trade_oracle API (8091)。${message}`);
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const message = simplifyErrorMessage(text, res.status);
    throw new Error(message);
  }

  return (await res.json()) as T;
}
