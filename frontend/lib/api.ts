import "server-only";
import { getAccessToken } from "./cookies";

// Not NEXT_PUBLIC_ — this value never needs to reach the browser, because
// every call to the backend happens from server code (Server Components,
// Server Actions, Route Handlers). The browser only ever talks to this
// Next.js server; it never calls FastAPI directly. One side effect worth
// noticing: the backend's CORS_ORIGINS setting (app/core/config.py) is
// there for the case where browser JS calls the API straight — since this
// app deliberately never does that for anything requiring the access
// token, CORS never actually comes into play here.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000/api/v1";

// Mirrors the backend's one error shape (see app/api/errors.py):
// {"error": "<code>", "detail": "<string or list of field errors>"}.
export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;

  constructor(status: number, code: string, detail: unknown) {
    super(`${code}: ${formatApiErrorDetail(detail)}`);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

type ApiFetchInit = RequestInit & {
  // Set to false for the one request that happens *before* we have a
  // token: logging in.
  auth?: boolean;
};

export async function apiFetch<T>(path: string, init: ApiFetchInit = {}): Promise<T> {
  const { auth = true, headers, ...rest } = init;

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Content-Type", "application/json");

  if (auth) {
    const token = await getAccessToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  // cache: "no-store" — this data changes whenever someone creates or
  // deactivates a user, so we always want a fresh request rather than
  // Next's default fetch caching. This is the "server-side data fetching"
  // pattern: plain fetch, awaited directly in a Server Component.
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.error ?? "unknown_error",
      body?.detail ?? "Something went wrong."
    );
  }

  // DELETE returns a small {"detail": "..."} body in this API, not 204 —
  // res.json() works for every route this app calls.
  return res.json() as Promise<T>;
}

// Turns the backend's validation shape (a list of {field, message}) into one
// readable line. GET /users/{bad-uuid} and a too-short password both come
// back through here.

export function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "message" in d ? String(d.message) : String(d)))
      .join(" ");
  }
  return "Something went wrong.";
}
