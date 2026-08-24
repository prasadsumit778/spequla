"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@workos-inc/authkit-nextjs/components";
import { SETTINGS_ITEM, showsSettings, visibleGroups } from "@/lib/nav";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/components/ui/cn";
import { Skeleton } from "@/components/ui/States";
import Icon from "./Icon";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, role, loading } = useAuth();
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  if (loading) return <BootScreen state="loading" />;
  if (!user) return <BootScreen state="signing-in" />;

  return (
    <div className="min-h-screen lg:flex">
      {/* Desktop rail */}
      <Sidebar role={role} pathname={pathname} className="hidden lg:flex" />

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            aria-label="Close navigation"
            className="absolute inset-0 bg-ink/40"
            onClick={() => setDrawerOpen(false)}
          />
          <Sidebar role={role} pathname={pathname} className="relative z-50 flex h-full w-64 shadow-raised" />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenNav={() => setDrawerOpen(true)} />
        <main className="mx-auto w-full max-w-[1360px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        <Footer />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ sidebar */

function Sidebar({
  role,
  pathname,
  className,
}: {
  role: string | null | undefined;
  pathname: string;
  className?: string;
}) {
  const groups = visibleGroups(role);
  return (
    <nav
      aria-label="Main"
      className={cn(
        "w-64 shrink-0 flex-col gap-1 overflow-y-auto bg-brand-900 px-3 pt-4 pb-6 lg:sticky lg:top-0 lg:h-screen",
        className
      )}
    >
      <Link href="/overview" className="mb-5 flex items-center gap-2.5 px-2 py-1">
        <Wordmark />
      </Link>

      {groups.map((group) => (
        <div key={group.heading} className="mb-4">
          <p className="px-2 pb-1.5 text-[10px] font-semibold tracking-[0.1em] text-brand-300 uppercase">
            {group.heading}
          </p>
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.href}>
                <NavLink href={item.href} label={item.label} icon={item.icon} pathname={pathname} title={item.blurb} />
              </li>
            ))}
          </ul>
        </div>
      ))}

      {showsSettings(role) && (
        <div className="mt-auto border-t border-brand-800 pt-3">
          <NavLink
            href={SETTINGS_ITEM.href}
            label={SETTINGS_ITEM.label}
            icon={SETTINGS_ITEM.icon}
            pathname={pathname}
            title={SETTINGS_ITEM.blurb}
          />
        </div>
      )}
    </nav>
  );
}

function NavLink({
  href,
  label,
  icon,
  pathname,
  title,
}: {
  href: string;
  label: string;
  icon: Parameters<typeof Icon>[0]["name"];
  pathname: string;
  title: string;
}) {
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
      title={title}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-control px-2.5 py-[7px] text-[13.5px] transition-colors",
        active
          ? "bg-brand-700 font-semibold text-white"
          : "text-brand-100 hover:bg-brand-800 hover:text-white"
      )}
    >
      <Icon name={icon} className={cn("h-[18px] w-[18px] shrink-0", active ? "text-white" : "text-brand-300")} />
      <span className="truncate">{label}</span>
    </Link>
  );
}

function Wordmark() {
  return (
    <>
      <span
        className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-brand-500 text-[13px] font-bold text-white"
        aria-hidden="true"
      >
        S
      </span>
      <span className="text-[15px] font-semibold tracking-[0.14em] text-white">SPEQULA</span>
    </>
  );
}

/* ------------------------------------------------------------------- topbar */

function TopBar({ onOpenNav }: { onOpenNav: () => void }) {
  const { user, role, signOut } = useAuth();
  const { entityId, setEntityId, profile, setProfile } = useWorkspace();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1360px] items-center gap-3 px-4 py-2.5 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onOpenNav}
          aria-label="Open navigation"
          className="-ml-1 rounded-control p-1.5 text-ink-muted hover:bg-surface-sunken lg:hidden"
        >
          <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <path d="M3.5 6h13M3.5 10h13M3.5 14h13" strokeLinecap="round" />
          </svg>
        </button>

        <div className="flex items-center gap-2 lg:hidden">
          <Wordmark />
        </div>

        {/* Which company, and which of the two profiles. Asked once, here,
            rather than on every screen. */}
        <div className="ml-auto flex items-center gap-2">
          <div className="hidden items-center gap-1.5 sm:flex">
            <label htmlFor="workspace-entity" className="label-caps">
              Entity
            </label>
            <input
              id="workspace-entity"
              type="number"
              min={1}
              value={entityId}
              onChange={(e) => setEntityId(Number(e.target.value))}
              className="h-8 w-16 rounded-control border border-line-strong bg-surface px-2 text-[13px] tabular-nums"
            />
          </div>
          <div className="hidden items-center gap-1.5 sm:flex">
            <label htmlFor="workspace-profile" className="label-caps">
              Profile
            </label>
            <select
              id="workspace-profile"
              value={profile}
              onChange={(e) => setProfile(e.target.value as "manufacturing" | "consumer")}
              className="h-8 cursor-pointer rounded-control border border-line-strong bg-surface px-2 pr-6 text-[13px]"
            >
              <option value="manufacturing">Manufacturing</option>
              <option value="consumer">Consumer</option>
            </select>
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={menuOpen}
              aria-haspopup="menu"
              className="flex items-center gap-2 rounded-control border border-line px-2 py-1 hover:bg-surface-sunken"
            >
              <span
                className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-[11px] font-semibold text-brand-700"
                aria-hidden="true"
              >
                {(user?.email || "?").slice(0, 1).toUpperCase()}
              </span>
              <span className="hidden max-w-[180px] truncate text-[13px] text-ink-soft sm:inline">
                {user?.email}
              </span>
              <svg viewBox="0 0 12 12" className="h-3 w-3 text-ink-faint" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <path d="m3 4.5 3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            {menuOpen && (
              <>
                <button className="fixed inset-0 z-10 cursor-default" aria-hidden="true" onClick={() => setMenuOpen(false)} />
                <div
                  role="menu"
                  className="absolute right-0 z-20 mt-1.5 w-60 rounded-card border border-line bg-surface p-1 shadow-raised"
                >
                  <div className="border-b border-line px-3 py-2">
                    <p className="truncate text-[13px] font-medium text-ink">{user?.email}</p>
                    <p className="mt-0.5 text-[12px] text-ink-muted">
                      {role ? roleLabel(role) : "No role assigned"}
                    </p>
                  </div>
                  <div className="px-3 py-2 sm:hidden">
                    <p className="text-[12px] text-ink-muted">
                      Entity {entityId} · {profile === "manufacturing" ? "Manufacturing" : "Consumer"}
                    </p>
                  </div>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => signOut()}
                    className="w-full rounded-control px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-surface-sunken"
                  >
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

export function roleLabel(role: string): string {
  switch (role) {
    case "promoter":
      return "Promoter";
    case "client_finance_lead":
      return "Finance lead";
    case "spequla_analyst":
      return "SPEQULA analyst";
    case "admin":
      return "Admin";
    default:
      return role;
  }
}

/* ------------------------------------------------------------------- footer */

function Footer() {
  return (
    <footer className="mx-auto w-full max-w-[1360px] px-4 pt-2 pb-8 text-[12px] text-ink-faint sm:px-6 lg:px-8">
      Every figure in SPEQULA carries a citation back to the rows it came from. A figure that cannot be traced is
      not shown.
    </footer>
  );
}

/* -------------------------------------------------------------- boot screen */

function BootScreen({ state }: { state: "loading" | "signing-in" }) {
  return (
    <div className="min-h-screen lg:flex">
      <div className="hidden w-64 shrink-0 flex-col bg-brand-900 px-3 pt-4 lg:flex">
        <div className="mb-6 flex items-center gap-2.5 px-2 py-1">
          <Wordmark />
        </div>
        <div className="space-y-2 px-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-7 animate-pulse rounded bg-brand-800" />
          ))}
        </div>
      </div>
      <div className="flex flex-1 flex-col">
        <div className="border-b border-line bg-surface px-6 py-3">
          <Skeleton className="ml-auto h-7 w-48" />
        </div>
        <div className="mx-auto w-full max-w-[1360px] px-6 py-8">
          {state === "signing-in" ? (
            <p className="text-sm text-ink-muted">Signing you in…</p>
          ) : (
            <div className="space-y-4">
              <Skeleton className="h-7 w-56" />
              <Skeleton className="h-4 w-80" />
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-28 rounded-card" />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
