import type { Role } from "@/lib/types";

// Plain presentational piece. It takes props and returns markup — nothing
// about that requires the browser, so it stays a (default) Server
// Component, same as most of the small pieces in this app.
export function RoleBadge({ role }: { role: Role }) {
  const isAdmin = role === "admin";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        isAdmin
          ? "bg-indigo-100 text-indigo-700"
          : "bg-slate-100 text-slate-600"
      }`}
    >
      {role}
    </span>
  );
}
