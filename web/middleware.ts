// WorkOS AuthKit session management. Protects every page under this app --
// per corpus/02 section 2, there is no unauthenticated screen in SPEQULA.
import { authkitMiddleware } from "@workos-inc/authkit-nextjs";

export default authkitMiddleware();

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
