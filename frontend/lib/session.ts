import "server-only";
import { cache } from "react";
import { apiFetch, ApiError } from "./api";
import type { User } from "./types";

import { getAccessToken, setAccessToken, clearAccessToken } from "./cookies";

// `cache()` (from "react") dedupes this per request: both the layout's
// <NavBar /> and a page can call getSessionUser() and only one network call
// to GET /auth/me actually happens for that request. Without this, every
// Server Component that needs "who is logged in" would re-fetch it.
export const getSessionUser = cache(async (): Promise<User | null> => {
  const token = await getAccessToken();
  if (!token) return null;

  try {
    return await apiFetch<User>("/auth/me");
  } catch (err) {
    // An expired or otherwise invalid token behaves the same as "logged
    // out" from the UI's point of view — we don't crash the page over it.
    if (err instanceof ApiError) return null;
    throw err;
  }
});
