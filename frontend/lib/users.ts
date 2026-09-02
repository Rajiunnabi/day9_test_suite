import "server-only";
import { apiFetch } from "./api";
import type { User } from "./types";

// This is the file Day 10's README said Day 11 would replace: same idea
// (a small data-access layer the pages call into) but every function here
// makes a real HTTP request to the FastAPI backend instead of reading an
// in-memory array. The page components (app/page.tsx, app/users/page.tsx,
// app/users/[id]/page.tsx) barely had to change shape for that swap.

export type UsersPage = {
  items: User[];
  total: number;
  limit: number;
  offset: number;
};

// The real API only supports `q` (search by name/email), `limit` and
// `offset` — no role filter, no custom sort. That is a genuine constraint
// of the backend (see app/repositories/user.py: UserRepository.search),
// not a simplification made for this exercise. It's why role-filtering and
// "sort by name" live client-side in UserListClient instead of as URL
// params here: the API has nothing to send them to.
export async function listUsers(params: {
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<UsersPage> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  qs.set("limit", String(params.limit ?? 50));
  qs.set("offset", String(params.offset ?? 0));

  return apiFetch<UsersPage>(`/users?${qs.toString()}`);
}

export async function getUser(publicId: string): Promise<User> {
  return apiFetch<User>(`/users/${publicId}`);
}

export type NewUserInput = {
  email: string;
  full_name: string;
  phone: string | null;
  password: string;
};

// POST /users always creates the new account with role "user" — the
// service (app/services/user.py) hardcodes that and ignores any role sent
// to it. Promoting someone to admin is a separate endpoint
// (PATCH /users/{id}/role, admin only) that this small app doesn't expose
// a screen for.
export async function createUser(input: NewUserInput): Promise<User> {
  return apiFetch<User>("/users", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// Soft-delete. Used from the Route Handler (app/api/users/[id]/route.ts),
// which is what the client-side "Deactivate" button actually calls — see
// that file for why this isn't called directly from the browser.
export async function deactivateUser(publicId: string): Promise<{ detail: string }> {
  return apiFetch<{ detail: string }>(`/users/${publicId}`, { method: "DELETE" });
}
