import Link from "next/link";

// A nested layout: only wraps routes under /users (list, /users/[id],
// /users/new). It sits inside the root layout — both are mounted at once,
// so navigating between "All users" and "Add user" only swaps the part
// below this header, not the NavBar above it or this header itself.
//
// Server Component again: it's static chrome around whatever page is
// active, no state or events of its own.
export default function UsersLayout({ children }: LayoutProps<"/users">) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-semibold">Users</h1>
          <p className="text-sm text-slate-500">
            Directory of everyone with an account.
          </p>
        </div>
        <Link
          href="/users/new"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
        >
          Add user
        </Link>
      </div>
      {children}
    </div>
  );
}
