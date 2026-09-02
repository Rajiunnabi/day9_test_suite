"use client";

import { useState } from "react";

// "use client" is needed here for one reason: this component calls
// useState and attaches an onClick handler. Both only make sense once the
// component is running in the browser, so this is where the server/client
// boundary has to be drawn.
//
// Contrast this with <SearchBox /> in app/users — that one also has client
// state, but it deliberately pushes that state into the URL (searchParams)
// instead of keeping it here. This component is the other case: state
// that is genuinely local and disposable. If the page reloads, it's fine
// for this menu to just close — nobody needs to bookmark "the
// notifications bell was open".
const seedNotifications = [
  "Farhana Ahmed joined last week",
  "2 accounts are missing a phone number",
];

export function NotificationsMenu() {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-full border border-slate-300 px-3 py-1 text-slate-600 hover:bg-slate-50"
        aria-expanded={open}
      >
        Notices ({seedNotifications.length})
      </button>

      {open && (
        <div className="absolute right-0 z-10 mt-2 w-64 rounded-md border border-slate-200 bg-white p-3 shadow-lg">
          <ul className="space-y-2 text-sm text-slate-600">
            {seedNotifications.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
