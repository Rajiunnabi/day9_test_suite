import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getUser } from "@/lib/users";
import { getSessionUser } from "@/lib/session";
import { ApiError } from "@/lib/api";
import { RoleBadge } from "@/components/RoleBadge";

// The folder name [id] makes this a dynamic route: /users/anything renders
// this page with params.id === "anything". Like searchParams, `params` is
// a Promise in Next 16.
export default async function UserDetailPage({
  params,
}: PageProps<"/users/[id]">) {
  const { id } = await params;

  const sessionUser = await getSessionUser();
  if (!sessionUser) redirect("/login");

  let user;
  try {
    user = await getUser(id);
  } catch (err) {
    if (err instanceof ApiError) {
      // 404: no such user — hand off to app/not-found.tsx.
      if (err.status === 404) notFound();
      // 401: the token died between the layout's check and this fetch
      // (e.g. it just expired) — send them to log in again.
      if (err.status === 401) redirect("/login?expired=1");
      // Anything else (a malformed id gives 422, the API being down gives
      // a network error) — rethrow so app/users/error.tsx can show it.
      // That's a REAL backend error, not the simulated one Day 10 used.
    }
    throw err;
  }

  return (
    <div className="max-w-md space-y-4">
      <Link href="/users" className="text-sm text-slate-500 hover:underline">
        ← Back to users
      </Link>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">{user.full_name}</h2>
          <RoleBadge role={user.role} />
        </div>
        <dl className="mt-4 space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500">Email</dt>
            <dd>{user.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Phone</dt>
            <dd>{user.phone ?? "—"}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Joined</dt>
            <dd>{new Date(user.created_at).toLocaleDateString()}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
