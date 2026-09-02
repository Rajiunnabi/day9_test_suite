import { NextResponse } from "next/server";
import { deactivateUser } from "@/lib/users";
import { ApiError } from "@/lib/api";

// A Route Handler: a plain API endpoint at /api/users/[id], same-origin
// with the app. This is the "direct API call" side of the contrast the Day
// 11 focus list asks about — compare with lib/actions.ts, where creating a
// user goes through a Server Action instead.
//
// Why deactivate goes through THIS instead of a Server Action: it's called
// from a Client Component (UserListClient) with plain fetch() so it can
// pair with useOptimistic — the row needs to disappear immediately, before
// the network call resolves, which is a client-side concern a form submit
// isn't shaped for. The access token itself never appears in that fetch
// call, because it's an httpOnly cookie the browser can't read; this route
// runs on the server, reads the cookie there, and attaches it to the real
// request to FastAPI. The browser only ever talks to this same-origin
// route, never to :8000 directly.
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const result = await deactivateUser(id);
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      // Pass the backend's own {error, detail} shape straight through, so
      // the client only has to learn to parse one error format.
      return NextResponse.json({ error: err.code, detail: err.detail }, { status: err.status });
    }
    return NextResponse.json(
      { error: "internal_error", detail: "Something went wrong." },
      { status: 500 }
    );
  }
}
