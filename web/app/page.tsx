import Link from "next/link";
import { withAuth } from "@workos-inc/authkit-nextjs";

export default async function Home() {
  const { user } = await withAuth();

  return (
    <div>
      <h1>SPEQULA</h1>
      <p>Sprint 1 scope: upload a trial balance, chart of accounts or general ledger file, and see load run status.</p>
      {user ? (
        <p>
          Signed in as {user.email}. <Link href="/upload">Go to Upload</Link> ·{" "}
          <Link href="/load-runs">Go to Load runs</Link>
        </p>
      ) : (
        <p>Redirecting to sign-in...</p>
      )}
    </div>
  );
}
