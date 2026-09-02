import { redirect } from "next/navigation";

// /settings on its own has nothing to show — it just picks a default tab.
// redirect() here runs on the server before any HTML is sent, so the
// browser never sees an empty /settings page flash by.
export default function SettingsIndexPage() {
  redirect("/settings/profile");
}
