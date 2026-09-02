import Link from "next/link";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/session";
import { listUsers } from "@/lib/users";
import { SearchBox } from "@/components/SearchBox";
import { UserListClient } from "@/components/UserListClient";

// `searchParams` is how a Server Component reads the URL's query string. In
// Next.js 16 it's a Promise you await — that's what lets Next start
// rendering before the params are even resolved.
export default async function UsersPage({
  searchParams,
}: PageProps<"/users">) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q : "";

  // GET /users requires a logged-in user (any role) — see AdminUser vs
  // CurrentUser in app/api/deps.py. No cookie, no point calling the API.
  const user = await getSessionUser();
  if (!user) redirect("/login");

  // Real, server-side data fetching: await a function that awaits fetch(),
  // right here in the Server Component. No client-side loading state is
  // needed for this part — loading.tsx covers the wait automatically.
  const { items, total } = await listUsers({ q, limit: 50 });

  return (
    <div className="space-y-4">
      <SearchBox q={q} />

      <p className="text-sm text-slate-500">
        {total} user{total === 1 ? "" : "s"} match{q ? ` "${q}"` : ""}
        {total > items.length ? ` (showing the first ${items.length})` : ""}.
        Role and sort below run in your browser over this page — the API
        itself only understands search.
      </p>

      <UserListClient initialUsers={items} />

      <p className="text-xs text-slate-400">
        Try{" "}
        <Link href="/users/not-a-real-id" className="underline">
          /users/not-a-real-id
        </Link>{" "}
        to see a real backend error land in the error boundary below.
      </p>
    </div>
  );
}
