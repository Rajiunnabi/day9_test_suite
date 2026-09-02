"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { createUserAction, type CreateUserState } from "@/lib/actions";

// "use client" because this needs a pending state while the Server Action
// runs. The action itself (createUserAction) still executes on the server —
// "use client" marks where the *component* renders, not where the mutation
// logic runs.

const initialState: CreateUserState = {
  error: null,
  values: { email: "", full_name: "", phone: "", password: "" },
};

// Split out so useFormStatus can see the enclosing <form>'s pending state
// (it only works in a descendant of the <form>, not the component that
// renders the <form> tag itself).
function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
    >
      {pending ? "Creating…" : "Create user"}
    </button>
  );
}

export function NewUserForm() {
  const [state, formAction] = useActionState(createUserAction, initialState);

  return (
    <form action={formAction} className="max-w-md space-y-4">
      {state.error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {state.error}
        </p>
      )}

      <div>
        <label className="block text-sm font-medium text-slate-700">
          Full name
        </label>
        <input
          name="full_name"
          defaultValue={state.values.full_name}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700">
          Email
        </label>
        <input
          type="email"
          name="email"
          defaultValue={state.values.email}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700">
          Phone (optional)
        </label>
        <input
          name="phone"
          defaultValue={state.values.phone}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700">
          Password
        </label>
        <input
          type="password"
          name="password"
          minLength={8}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          required
        />
        <p className="mt-1 text-xs text-slate-400">
          At least 8 characters — this is what the new user logs in with.
        </p>
      </div>

      <p className="text-xs text-slate-400">
        New accounts are always created with the &quot;user&quot; role. The
        API has a separate admin-only endpoint for promoting someone to
        admin, which this screen doesn&apos;t expose.
      </p>

      <SubmitButton />
    </form>
  );
}
