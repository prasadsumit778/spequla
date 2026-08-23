// Where WorkOS redirects back to after a user signs in. Must match
// NEXT_PUBLIC_WORKOS_REDIRECT_URI and the redirect URI configured in the
// WorkOS dashboard exactly.
import { handleAuth } from "@workos-inc/authkit-nextjs";

export const GET = handleAuth({ returnPathname: "/" });
