const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const unsafeErrorDetail =
  /\b(?:sql|postgres(?:ql)?|database|password|credentials?|traceback|stack trace)\b|:\/\/[^/\s:@]+:[^/\s@]+@/i;
let csrfToken: string | null = null;

export function setCsrfToken(value: string | null): void {
  csrfToken = value;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function userFacingError(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError) || error.status >= 500) return fallback;
  if (unsafeErrorDetail.test(error.message)) return fallback;
  return error.message;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (
    options.method &&
    !["GET", "HEAD", "OPTIONS"].includes(options.method.toUpperCase()) &&
    csrfToken
  ) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (
        typeof body.detail === "string" &&
        !unsafeErrorDetail.test(body.detail)
      ) {
        message = body.detail;
      }
    } catch {
      // Retain the safe status-based message for non-JSON responses.
    }
    if (response.status === 401) setCsrfToken(null);
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function downloadCsv(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (!response.ok) throw new ApiError("CSV export failed.", response.status);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "orbit-records.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}
