export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`API Error ${status}`);
    this.status = status;
    this.body = body;
  }
}

/** Thrown when a request exceeds its timeout (or its AbortSignal fires). */
export class TimeoutError extends Error {
  constructor(path: string) {
    super(`Request timed out: ${path}`);
    this.name = "TimeoutError";
  }
}

/** Default per-request timeout. Override via `apiRequest(path, { timeoutMs })`. */
export const DEFAULT_TIMEOUT_MS = 30_000;

type ApiInit = Omit<RequestInit, "signal"> & {
  /** Extra signal to combine with the timeout (e.g. React Query's). */
  signal?: AbortSignal;
  /** Per-request timeout; `0` disables it. */
  timeoutMs?: number;
};

function buildHeaders(init: ApiInit): Headers {
  const headers = new Headers(init.headers);
  // The backend's destructive endpoints require this (#99): a cross-origin
  // simple request can't set a custom header without a CORS preflight, which
  // the origin allow-list blocks for unknown origins.
  headers.set("X-Requested-With", "XMLHttpRequest");
  headers.set("Accept", "application/json");
  // Only declare a JSON body — never on GET, and let the browser set the
  // multipart boundary for FormData bodies.
  if (typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

/**
 * The single fetch primitive. Adds default headers, a timeout, and uniform
 * `ApiError` / `TimeoutError` handling. Returns the parsed JSON body (or
 * `undefined` for an empty 2xx response).
 */
export async function apiRequest<T>(path: string, init: ApiInit = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: callerSignal, ...rest } = init;

  const signals: AbortSignal[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  if (timeoutMs > 0) {
    const ac = new AbortController();
    timer = setTimeout(() => ac.abort(), timeoutMs);
    signals.push(ac.signal);
  }
  if (callerSignal) signals.push(callerSignal);
  const signal = signals.length ? AbortSignal.any(signals) : undefined;

  let res: Response;
  try {
    res = await fetch(path, { ...rest, headers: buildHeaders(init), signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new TimeoutError(path);
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }

  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = null;
  }

  if (!res.ok) {
    throw new ApiError(res.status, body ?? null);
  }
  return body as T;
}

export function apiGet<T>(path: string, init?: ApiInit): Promise<T> {
  return apiRequest<T>(path, init);
}

export function apiPost<T>(path: string, data: unknown, init?: ApiInit): Promise<T> {
  return apiRequest<T>(path, { ...init, method: "POST", body: JSON.stringify(data) });
}

export function apiPut<T>(path: string, data: unknown, init?: ApiInit): Promise<T> {
  return apiRequest<T>(path, { ...init, method: "PUT", body: JSON.stringify(data) });
}

export function apiPatch<T>(path: string, data: unknown, init?: ApiInit): Promise<T> {
  return apiRequest<T>(path, { ...init, method: "PATCH", body: JSON.stringify(data) });
}

export function apiDelete<T = void>(path: string, init?: ApiInit): Promise<T> {
  return apiRequest<T>(path, { ...init, method: "DELETE" });
}
