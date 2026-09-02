import Link from "next/link";

// A second nested layout, deliberately different in shape from
// app/users/layout.tsx: that one wraps a list + a dynamic route, this one
// wraps a fixed pair of tabs. Nesting isn't one pattern — it's "whatever
// chrome a section of the URL tree should share", decided per section.
export default function SettingsLayout({
  children,
}: LayoutProps<"/settings">) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <div className="flex gap-4 border-b border-slate-200 text-sm">
        <Link
          href="/settings/profile"
          className="border-b-2 border-transparent px-1 pb-3 hover:border-slate-400"
        >
          Profile
        </Link>
        <Link
          href="/settings/notifications"
          className="border-b-2 border-transparent px-1 pb-3 hover:border-slate-400"
        >
          Notifications
        </Link>
      </div>
      {children}
    </div>
  );
}
