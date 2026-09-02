export default function ProfileSettingsPage() {
  return (
    <div className="max-w-md space-y-3 text-sm text-slate-600">
      <p>
        Static placeholder content — the point of this route is the nested
        layout and tab navigation above, not this text.
      </p>
      <p>
        Because this page and /settings/notifications share
        app/settings/layout.tsx, switching tabs never re-renders the tab
        bar itself.
      </p>
    </div>
  );
}
