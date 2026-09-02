"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

// "use client" because this reads and writes the URL live as the person
// types, which needs an event handler and browser APIs.
//
// This is the ONE filter that's kept in the URL instead of useState. Why:
// the real API's GET /users?q= actually does the filtering in the
// database, so ?q= reflects a real server round-trip — the list page (a
// Server Component) reads it via searchParams and re-fetches. Role and
// sort don't get the same treatment (see UserListClient) because the API
// has no ?role= or ?sort= to send them to.
export function SearchBox({ q }: { q: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function update(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set("q", value);
    } else {
      params.delete("q");
    }
    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
    });
  }

  return (
    <div className="flex items-center gap-2">
      <input
        defaultValue={q}
        onChange={(e) => update(e.target.value)}
        placeholder="Search name or email"
        className="w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
      />
      {isPending && <span className="text-xs text-slate-400">Searching</span>}
    </div>
  );
}
