"use client";

import { useMemo, useOptimistic, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Role, User } from "@/lib/types";
import { RoleBadge } from "./RoleBadge";

// "use client" for three reasons stacked in one component: local state
// (role filter, sort), an optimistic update, and a fetch() call with a
// click handler. None of that can happen in a Server Component.
//
// `initialUsers` is the page the Server Component already fetched from the
// real API (see app/users/page.tsx) — this component never fetches the
// list itself. Role and sort then run entirely in the browser, over
// whatever page that was, because the backend has nothing to send a
// ?role= or ?sort= to (see the comment in lib/users.ts).
export function UserListClient({ initialUsers }: { initialUsers: User[] }) {
  const router = useRouter();
  const [roleFilter, setRoleFilter] = useState<Role | "all">("all");
  const [sort, setSort] = useState<"newest" | "name">("newest");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  // useOptimistic's second argument is a reducer: (currentState, action) =>
  // nextState. Calling removeOptimistically(id) immediately re-renders with
  // that user filtered out — before the DELETE request has even resolved.
  // Once router.refresh() below re-fetches initialUsers from the server,
  // this optimistic layer resets to match reality: it disappears for good
  // on success, or reappears if the delete actually failed.
  const [optimisticUsers, removeOptimistically] = useOptimistic(
    initialUsers,
    (state, removedId: string) => state.filter((u) => u.public_id !== removedId)
  );

  const visible = useMemo(() => {
    let list = optimisticUsers;
    if (roleFilter !== "all") {
      list = list.filter((u) => u.role === roleFilter);
    }
    if (sort === "name") {
      list = [...list].sort((a, b) => a.full_name.localeCompare(b.full_name));
    }
    // "newest" needs no client-side sort — the API already returns rows
    // ordered by created_at desc (see UserRepository.search).
    return list;
  }, [optimisticUsers, roleFilter, sort]);

  function handleDeactivate(id: string, name: string) {
    if (!confirm(`Deactivate ${name}? They will no longer be able to log in.`)) {
      return;
    }
    setRowError(null);
    setPendingId(id);

    startTransition(async () => {
      removeOptimistically(id);
      try {
        const res = await fetch(`/api/users/${id}`, { method: "DELETE" });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(
            typeof body?.detail === "string" ? body.detail : "Could not deactivate that user."
          );
        }
      } catch (err) {
        setRowError(err instanceof Error ? err.message : "Could not deactivate that user.");
      } finally {
        setPendingId(null);
        // Re-sync with the server either way: confirms the removal on
        // success, and un-does the optimistic removal (by re-supplying the
        // real initialUsers) if the request actually failed.
        router.refresh();
      }
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as Role | "all")}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="all">All roles</option>
          <option value="admin">Admin</option>
          <option value="user">User</option>
        </select>

        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "newest" | "name")}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="newest">Sort: newest</option>
          <option value="name">Sort: name</option>
        </select>

        <span className="text-xs text-slate-400">
          (runs in your browser, not the server)
        </span>
      </div>

      {rowError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{rowError}</p>
      )}

      {visible.length === 0 ? (
        <p className="text-sm text-slate-500">No users match that filter.</p>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {visible.map((user) => (
            <li
              key={user.public_id}
              className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
            >
              <Link href={`/users/${user.public_id}`} className="min-w-0 flex-1">
                <p className="truncate font-medium">{user.full_name}</p>
                <p className="truncate text-sm text-slate-500">{user.email}</p>
              </Link>
              <div className="flex items-center gap-3">
                <RoleBadge role={user.role} />
                <button
                  onClick={() => handleDeactivate(user.public_id, user.full_name)}
                  disabled={pendingId === user.public_id}
                  className="text-sm text-red-600 hover:underline disabled:opacity-50"
                >
                  {pendingId === user.public_id ? "Deactivating…" : "Deactivate"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
