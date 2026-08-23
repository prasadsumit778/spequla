import type { Metadata } from "next";
import Link from "next/link";
import { withAuth } from "@workos-inc/authkit-nextjs";
import { AuthKitProvider } from "@workos-inc/authkit-nextjs/components";
import AuthNav from "@/components/AuthNav";

export const metadata: Metadata = {
  title: "SPEQULA",
  description: "Upload, mapping, statements.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const auth = await withAuth({ ensureSignedIn: true });
  const { accessToken, ...initialAuth } = auth;

  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, color: "#1a1a2e" }}>
        <AuthKitProvider initialAuth={initialAuth}>
          <nav style={{ display: "flex", gap: 16, padding: "12px 24px", borderBottom: "1px solid #ddd" }}>
            <strong>SPEQULA</strong>
            <Link href="/upload">Upload</Link>
            <Link href="/load-runs">Load runs</Link>
            <Link href="/mapping">Mapping</Link>
            <Link href="/statements">Statements</Link>
            <Link href="/overview">Overview</Link>
            <Link href="/data-health">Data health</Link>
            <Link href="/exceptions">Exceptions</Link>
            <Link href="/ask">Ask</Link>
            <Link href="/reports">Reports</Link>
            <Link href="/operating">Operating</Link>
            <Link href="/settings">Settings</Link>
            <AuthNav />
          </nav>
          <main style={{ padding: 24, maxWidth: 900 }}>{children}</main>
        </AuthKitProvider>
      </body>
    </html>
  );
}
