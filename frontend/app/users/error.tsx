"use client";

import { useEffect } from "react";

// error.tsx MUST be a Client Component — React error boundaries only work
// as class-like runtime behavior in the browser, so Next.js requires
// "use client" here even though everything else in this section is a
// Server Component. Next wraps the segment in this boundary automatically;
// when a Server Component throws (see the ?fail=1 check in page.tsx), this
// is what renders instead of the crashed page.
export default function UsersError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
      <p className="font-medium text-red-800">Something went wrong.</p>
      <p className="mt-1 text-sm text-red-700">{error.message}</p>
      <button
        onClick={() => reset()}
        className="mt-4 rounded-md bg-red-700 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-800"
      >
        Try again
      </button>
    </div>
  );
}
