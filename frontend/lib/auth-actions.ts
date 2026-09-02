"use server";

import { redirect } from "next/navigation";
import { apiFetch, ApiError } from "./api";
import { setAccessToken, clearAccessToken } from "./cookies";

type TokenOut = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type LoginState = {
  error: string | null;
  email: string;
};

export async function loginAction(
  prevState: LoginState,
  formData: FormData
): Promise<LoginState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email || !password) {
    return { error: "Enter your email and password.", email };
  }

  try {
    // auth: false — there is no token yet, this call IS how we get one.
    const tokens = await apiFetch<TokenOut>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      auth: false,
    });

    await setAccessToken(tokens.access_token, tokens.expires_in);
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 401) {
        return { error: "Incorrect email or password.", email };
      }
      if (err.status === 429) {
        return { error: "Too many attempts. Try again in a few minutes.", email };
      }
      return { error: "Could not log in right now. Please try again.", email };
    }
    throw err;
  }

  redirect("/users");
}

// No form state to track here, so this doesn't need useActionState on the
// client — it's wired straight to a <form action={logoutAction}> in
// NavBar.tsx, which is itself a Server Component. Zero client JS involved
// in logging out.
export async function logoutAction() {
  await clearAccessToken();
  redirect("/login");
}
