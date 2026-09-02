// Next.js automatically wraps the page in <Suspense fallback={<Loading />}>
// using this file — no import, no wiring, just the filename. It's shown the
// moment you navigate to /users (or any child route while it loads) and
// disappears once the page's own await finishes. Try slow network in
// devtools, or just watch it flash on first navigation to /users.
export default function UsersLoading() {
  return (
    <div className="space-y-4">
      <div className="h-9 w-80 animate-pulse rounded-md bg-slate-200" />
      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-14 animate-pulse rounded-md bg-slate-100"
          />
        ))}
      </div>
    </div>
  );
}
