# Team Directory — Days 10–11 (Next.js App Router + a real backend)

A small multi-page app for practicing the App Router (Day 10), then
connecting it to the real FastAPI backend from the parent project (Day 11).
There's no mock data left — `lib/users.ts` calls the actual API.

## Run it

You need the backend running first (from the `day9_test_suite` project root,
one level up):

```bash
uv sync
uv run alembic upgrade head
uv run python -m scripts.create_admin you@example.com "Your Name"   # first admin
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

Then, in `frontend/`:

```bash
npm install
cp .env.local.example .env.local   # only if API_BASE_URL differs from the default
npm run dev
```

Open http://localhost:3000, log in with the admin account you just created,
and you'll land on a real, connected user list.

## The mental model, in plain terms

**Every component is a Server Component unless it says `"use client"` at the
top.** Server Components run on the server only — they can `await` data
directly, and none of their code is sent to the browser. Add `"use client"`
only when a component actually needs the browser: `useState`, `onClick`,
`useEffect`, or a browser-only API.

**Server state, UI state, and form state are three different things**, and
mixing them up is the usual source of bugs:
- **Server state** — the actual rows in Postgres, fetched fresh on every
  request in `lib/users.ts`. This app never caches it client-side; a
  `router.refresh()` or a page reload always shows what the database
  actually has.
- **UI state** — things only the browser needs to remember, like whether
  the notifications menu is open, or (this session) the role/sort dropdowns
  on `/users`. Plain `useState`.
- **Form state** — what's currently typed into a form, plus its
  pending/error/success status. Handled by `useActionState`, which is built
  for exactly this and avoids hand-rolling three separate `useState` calls
  per form.

## Where each Day 10 concept lives

| Concept | File |
|---|---|
| Root layout (shared shell) | `app/layout.tsx` |
| Nested layout #1 (list + dynamic route) | `app/users/layout.tsx` |
| Nested layout #2 (tabs) | `app/settings/layout.tsx` |
| Dynamic route (`[id]`) | `app/users/[id]/page.tsx` |
| Loading state (auto Suspense fallback) | `app/users/loading.tsx` |
| Error boundary, now catching a real backend error | `app/users/error.tsx` (try `/users/not-a-real-id`) |
| 404 / `notFound()`, now from a real 404 | `app/not-found.tsx`, used from `app/users/[id]/page.tsx` |
| Server Component rendering a Client Component | `components/NavBar.tsx` → `NotificationsMenu` |

## Where each Day 11 concept lives

| Concept | File |
|---|---|
| Server-only API client (auth header, error parsing) | `lib/api.ts` |
| httpOnly cookie session (read/write/clear) | `lib/cookies.ts` |
| "Who's logged in" — real request, deduped per-request | `lib/session.ts` (`getSessionUser`, wrapped in React's `cache()`) |
| Data-access layer calling the real API | `lib/users.ts` |
| **Server Action** for a mutation (form submit) | `lib/actions.ts` (`createUserAction`) + `components/NewUserForm.tsx` |
| **Direct API call** for a mutation (client `fetch`) | `app/api/users/[id]/route.ts` (Route Handler) + `components/UserListClient.tsx` (`fetch("/api/users/…")`) |
| Optimistic UI update | `components/UserListClient.tsx` (`useOptimistic`, the Deactivate button) |
| Login / logout Server Actions | `lib/auth-actions.ts` |
| Server-side data fetching (real `fetch`, awaited in a Server Component) | `app/page.tsx`, `app/users/page.tsx`, `app/users/[id]/page.tsx` |
| URL state driving a real server query | `components/SearchBox.tsx` writes `?q=`; `app/users/page.tsx` reads it and calls the API with it |
| Client-only state with nothing to send it to | `components/UserListClient.tsx` (role filter, sort — see below) |
| Handling a real 401 / 403 / 409 / 422 from the API | `lib/actions.ts` (`createUserAction`'s catch block) |

## Server Actions vs a direct API call — why this app uses both

**Creating a user** is a `<form>` a person fills in and submits, so it uses
a **Server Action** (`createUserAction`). That gets progressive enhancement
(it still works before the page's JS finishes loading) and built-in
pending/error state via `useActionState` — no separate API route needed.

**Deactivating a user** is a one-click button inside a list that also wants
an **optimistic update** — the row should disappear the instant you click,
before the network request resolves. That's a client-side concern a form
submit isn't shaped for, so it uses plain `fetch()` from a Client Component
instead, hitting a small Route Handler at `/api/users/[id]`.

That Route Handler exists — rather than the browser calling FastAPI
directly — because the access token is an **httpOnly cookie**: browser JS
(including this app's own Client Components) can't read it. The Route
Handler runs on the server, reads the cookie there, and attaches it to the
real request to FastAPI. The browser only ever talks to this same-origin
route; it never calls `localhost:8000` directly. One side effect worth
noticing: the backend's `CORS_ORIGINS` setting only matters for the case
where browser JS *does* call the API straight — since this app deliberately
never does that for anything needing the token, CORS never actually comes
into play here.

## A real constraint that shaped the UI: the API doesn't support role filtering or sort

`GET /users` only accepts `q`, `limit`, and `offset` (see
`app/repositories/user.py: UserRepository.search` in the backend) — no
`?role=` param, no custom sort. That's not a simplification made for this
exercise; it's how the real API is built. So:

- **Search** (`?q=`) is real server-side filtering — `SearchBox` writes it
  to the URL, `app/users/page.tsx` reads it and asks the database.
- **Role filter and sort** run entirely in the browser, in
  `UserListClient`, over whatever page of results the server already sent.
  The UI says as much ("runs in your browser, not the server") so it's
  never presented as something it isn't.

This is the "server-side vs client-side data fetching" focus topic showing
up as an honest answer to a real limitation, rather than a made-up example.

## A few simplifications, on purpose

- **No refresh-token flow.** The access token expires in 15 minutes
  (`ACCESS_TOKEN_EXPIRE_MINUTES` in the backend's `.env`); this app doesn't
  silently renew it. When a request comes back 401, the page just redirects
  to `/login?expired=1`. A production app would try the refresh token
  first — building that is a reasonable Day 12-style extension.
- **No "promote to admin" screen.** `POST /users` always creates the new
  account with role `"user"` (the backend hardcodes this — see
  `UserService.create`). There's a separate admin-only endpoint,
  `PATCH /users/{id}/role`, for promotions, but this app doesn't expose a
  screen for it.
- **The dashboard's admin count is approximate.** The API has no aggregate
  "count by role" endpoint, so `app/page.tsx` counts within the first page
  of results it already fetched rather than adding a new endpoint.
