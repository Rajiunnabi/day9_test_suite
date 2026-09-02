import Link from "next/link";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/session";
import { listUsers } from "@/lib/users";

// No "use client" — this awaits real data directly in the component body,
// something only a Server Component can do. It runs on the server, awaits
// listUsers() there, and the browser gets HTML with the numbers already
// filled in. No spinner on first load, because there's no client-side
// fetch to wait for.
export default async function DashboardPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  // The API has no dedicated "counts" endpoint, so this reads one page of
  // users and counts within it — total is exact (the API reports it), but
  // "admins" only reflects this page. A real dashboard would ask the
  // backend for that aggregate directly instead of approximating it here.
  const { items, total } = await listUsers({ limit: 100 });
  const admins = items.filter((u) => u.role === "admin").length;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-slate-600">
          Signed in as {user.full_name} ({user.role}).
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:max-w-md">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">Total users</p>
          <p className="text-3xl font-semibold">{total}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">
            Admins {total > items.length ? "(first 100)" : ""}
          </p>
          <p className="text-3xl font-semibold">{admins}</p>
        </div>
      </div>

      <div className="flex gap-3 text-sm">
        <Link
          href="/users"
          className="rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-700"
        >
          View users
        </Link>
        <Link
          href="/users/new"
          className="rounded-md border border-slate-300 px-4 py-2 font-medium hover:bg-slate-100"
        >
          Add a user
        </Link>
      </div>
    </div>
  );
}
