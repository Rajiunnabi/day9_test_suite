import "server-only";
import { cookies } from "next/headers";

// The access token lives in one place: an httpOnly cookie. "httpOnly" means
// browser JS (including our own Client Components) can never read it — only
// server code (Server Components, Server Actions, Route Handlers) can. That
// is deliberate: it is the whole reason a Client Component that wants to
// delete a user has to go through a Route Handler (see
// app/api/users/[id]/route.ts) instead of attaching the token itself.
const COOKIE_NAME = "access_token";

export async function getAccessToken(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(COOKIE_NAME)?.value ?? null;
}

// Only callable from a Server Action or Route Handler — Next forbids writing
// cookies from a Server Component render, on purpose: rendering should never
// have side effects.
export async function setAccessToken(token: string, expiresInSeconds: number) {
  const jar = await cookies();
  jar.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: expiresInSeconds,
  });
}

export async function clearAccessToken() {
  const jar = await cookies();
  jar.delete(COOKIE_NAME);
}
