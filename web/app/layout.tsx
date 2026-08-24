import type { Metadata, Viewport } from "next";
import { withAuth } from "@workos-inc/authkit-nextjs";
import { AuthKitProvider } from "@workos-inc/authkit-nextjs/components";
import AppShell from "@/components/app/AppShell";
import { WorkspaceProvider } from "@/lib/workspace";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SPEQULA",
    template: "%s · SPEQULA",
  },
  description:
    "Always-on FP&A: statements that tie to the books, every number traceable to the rows it came from.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#132434",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const auth = await withAuth({ ensureSignedIn: true });
  const { accessToken, ...initialAuth } = auth;

  return (
    <html lang="en-IN">
      <body>
        <AuthKitProvider initialAuth={initialAuth}>
          <WorkspaceProvider>
            <AppShell>{children}</AppShell>
          </WorkspaceProvider>
        </AuthKitProvider>
      </body>
    </html>
  );
}
