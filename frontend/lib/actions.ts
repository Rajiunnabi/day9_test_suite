"use server";

// A Server Action: a function that runs on the server but can be called
// directly from a form or a Client Component, without a hand-written API
// route. Next.js turns `action={createUserAction}` into a POST under the
// hood. This is the "Server Actions vs direct API calls" contrast the Day
// 11 focus list asks about — compare this file with
// app/api/users/[id]/route.ts, which handles the *other* mutation
// (deactivating a user) as a plain API route the client calls with fetch.
// Server Action here makes sense because this is a real <form> a person
// fills in and submits — it gets progressive enhancement (works before JS
// finishes loading) and built-in pending/error state via useActionState.

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createUser } from "./users";
import { ApiError, formatApiErrorDetail } from "./api";

export type CreateUserState = {
  error: string | null;
  values: { email: string; full_name: string; phone: string; password: string };
};

export async function createUserAction(
  prevState: CreateUserState,
  formData: FormData
): Promise<CreateUserState> {
  const email = String(formData.get("email") ?? "").trim();
  const full_name = String(formData.get("full_name") ?? "").trim();
  const phone = String(formData.get("phone") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  const values = { email, full_name, phone, password: "" }; // never echo the password back

  // Client-visible checks first, so an obvious mistake doesn't cost a round
  // trip. The backend (Pydantic) re-validates everything anyway — this is a
  // UX shortcut, not the real line of defense.
  if (!full_name) return { error: "Full name is required.", values };
  if (!email.includes("@")) return { error: "Enter a valid email address.", values };
  if (password.length < 8) {
    return { error: "Password must be at least 8 characters.", values };
  }

  try {
    await createUser({ email, full_name, phone: phone || null, password });
  } catch (err) {
    if (err instanceof ApiError) {
      // 401: the session cookie is missing or expired — not "this form is
      // wrong", so send them to log in again instead of showing a form error.
      if (err.status === 401) redirect("/login?expired=1");

      // 403: logged in, but the backend's `AdminUser` dependency rejected
      // the request because this account isn't an admin. The UI never hid
      // the form for non-admins — the API is what actually enforces this,
      // and this is that enforcement showing up as a real response.
      if (err.status === 403) {
        return {
          error: "Only admin accounts can create users. Your account isn't an admin.",
          values,
        };
      }
      if (err.status === 409) {
        return { error: formatApiErrorDetail(err.detail), values };
      }
      if (err.status === 422) {
        return { error: formatApiErrorDetail(err.detail), values };
      }
      return { error: "Could not create the user. Please try again.", values };
    }
    throw err;
  }

  // Tell Next.js /users is stale so it refetches instead of serving a
  // cached page with the old list.
  revalidatePath("/users");
  redirect("/users");
}
