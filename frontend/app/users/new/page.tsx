import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/session";
import { NewUserForm } from "@/components/NewUserForm";

// This page stays a Server Component — it has nothing to do besides check
// the session and render a heading. Wrapping the whole page in "use
// client" just because *one* piece needs interactivity is the mistake this
// avoids: only NewUserForm pays the client-JS cost.
export default async function NewUserPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  return (
    <div className="max-w-md space-y-4">
      <p className="text-sm text-slate-600">
        Submitting this calls a Server Action, which calls{" "}
        <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
          POST /api/v1/users
        </code>{" "}
        on the real backend using your session cookie. That endpoint is
        admin-only — if your account isn&apos;t an admin, the form will show
        the 403 the API sends back.
      </p>
      <NewUserForm />
    </div>
  );
}
