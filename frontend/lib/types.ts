// Shared shape for a "user" in this app.
//
// The field names match app/schemas/user.py (UserOut) on the FastAPI
// backend exactly: public_id, email, full_name, phone, role, created_at,
// updated_at. lib/users.ts fetches real rows in this shape from the API.

export type Role = "user" | "admin";

export type User = {
  public_id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  created_at: string; // ISO date string
  updated_at: string;
};
