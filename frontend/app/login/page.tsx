import { LoginForm } from "@/components/LoginForm";

// A plain Server Component wrapper, same pattern as app/users/new/page.tsx:
// the page itself has no state, so only the form underneath needs
// "use client".
export default async function LoginPage({
  searchParams,
}: PageProps<"/login">) {
  const params = await searchParams;
  const expired = params.expired === "1";

  return (
    <div className="mx-auto max-w-sm space-y-4">
      <h1 className="text-2xl font-semibold">Log in</h1>

      {expired && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Your session expired. Log in again.
        </p>
      )}

      <p className="text-sm text-slate-500">
        Use the admin account created with{" "}
        <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
          uv run python -m scripts.create_admin
        </code>{" "}
        in the backend project — that&apos;s what lets you reach the
        create-user form (it&apos;s admin-only on the API side).
      </p>

      <LoginForm />
    </div>
  );
}
