import Link from "next/link";
import { NotificationsMenu } from "./NotificationsMenu";
import { getSessionUser } from "@/lib/session";
import { logoutAction } from "@/lib/auth-actions";

// An async Server Component: it awaits getSessionUser() (which itself
// awaits a real fetch to GET /auth/me, deduped per-request via React's
// cache()) directly in the render, then sends the browser plain HTML —
// no client-side "checking who's logged in" spinner needed.
//
// It still renders one Client Component, <NotificationsMenu />. A Server
// Component can render a Client Component like this — that direction is
// always allowed. The reverse isn't, because by the time client code runs
// in the browser, the server is no longer around to render for it.
export async function NavBar() {
  const user = await getSessionUser();

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <Link href="/" className="font-semibold tracking-tight text-slate-900">
          Team Directory
        </Link>
         <nav className="flex items-center gap-6 text-sm">
          <Link href="/" className="text-slate-600 hover:text-slate-900">
            Dashboard
          </Link>
          <Link href="/users" className="text-slate-600 hover:text-slate-900">
            Users
          </Link>
          <Link href="/settings" className="text-slate-600 hover:text-slate-900">
            Settings
          </Link>

          {user ? (
            <>
              <NotificationsMenu />
              <span className="text-slate-400">
                {user.full_name} - {user.role}
              </span>
              {/* A Server Action wired straight to a form, in a Server
                  Component: logging out needs zero client-side JavaScript.
                  Compare with NotificationsMenu, which genuinely does. */}
              <form action={logoutAction}>
                <button
                  type="submit"
                  className="text-slate-600 hover:text-slate-900"
                >
                  Log out
                </button>
              </form>
            </>
          ) : (
            <Link href="/login" className="text-slate-600 hover:text-slate-900">
              Log in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
