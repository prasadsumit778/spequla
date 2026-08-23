"use client";

import { useAuth } from "@workos-inc/authkit-nextjs/components";

export default function AuthNav() {
  const { user, loading, signOut } = useAuth();

  if (loading) return <span>...</span>;

  if (!user) {
    // Sign-in is handled by the middleware redirecting to AuthKit for any
    // protected route -- there is no unauthenticated screen in SPEQULA,
    // per corpus/02 section 2. Visiting the app at all triggers it.
    return <span>Signing in...</span>;
  }

  return (
    <span style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
      <span>{user.email}</span>
      <button onClick={() => signOut()} style={{ padding: "4px 10px" }}>
        Sign out
      </button>
    </span>
  );
}
