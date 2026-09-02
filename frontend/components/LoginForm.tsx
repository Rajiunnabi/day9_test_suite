"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { loginAction, type LoginState } from "@/lib/auth-actions";

const initialState: LoginState = { error: null, email: "" };
function clearButton() {
  localStorage.clear();
}
function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      onClick={clearButton}
      disabled={pending}
      className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
    >
      {pending ? "Logging in…" : "Log in"}
    </button>
  );
}

export function LoginForm() {
  const [state, formAction] = useActionState(loginAction, initialState);

  return (
    <form action={formAction} className="space-y-4">
      {state.error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {state.error}
        </p>
      )}

      <div>
        <label className="block text-sm font-medium text-slate-700">Email</label>
        <input
          type="email"
          name="email"
          defaultValue={state.email}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700">Password</label>
        <input
          type="password"
          name="password"
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          required
        />
      </div>

      <SubmitButton />
    </form>
  );
}
