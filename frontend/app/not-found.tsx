import Link from "next/link";

// Handles two cases with one file: a URL that matches no route at all, and
// any page that calls notFound() explicitly (see app/users/[id]/page.tsx).
// Plain Server Component — no state, no handlers.
export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-slate-500">
        That user or page doesn&apos;t exist.
      </p>
      <Link
        href="/"
        className="mt-4 inline-block text-sm font-medium text-slate-900 underline"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
