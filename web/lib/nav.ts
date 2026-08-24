/**
 * The navigation model. corpus/08 section 2 lists the P0 screens; corpus/02
 * section 2 says who sees which of them -- "Promoter ... Financial overview,
 * Ask, Reports. No mapping screens, no exception queue."
 *
 * This is presentation, not enforcement. The backend is the access boundary
 * (src/api/deps/auth.py's require_role / require_upload_role); this only
 * decides what a role is offered, so a promoter is not handed a screen the
 * corpus says is not theirs.
 */

export type NavItem = {
  href: string;
  label: string;
  /** One line, shown on the home screen and as the sidebar tooltip. */
  blurb: string;
  icon: IconName;
};

export type NavGroup = { heading: string; items: NavItem[] };

export type IconName =
  | "overview"
  | "statements"
  | "operating"
  | "ask"
  | "reports"
  | "upload"
  | "loadRuns"
  | "mapping"
  | "dataHealth"
  | "exceptions"
  | "settings";

export const NAV_GROUPS: NavGroup[] = [
  {
    heading: "Financials",
    items: [
      { href: "/overview", label: "Overview", blurb: "The nine headline metrics for a period, each with its citation.", icon: "overview" },
      { href: "/statements", label: "Statements", blurb: "Profit and loss, and the balance sheet that has to balance.", icon: "statements" },
      { href: "/operating", label: "Operating metrics", blurb: "The consumer CM ladder, or manufacturing yield and cost per unit.", icon: "operating" },
      { href: "/ask", label: "Ask", blurb: "A question, an answer, and the query that produced it.", icon: "ask" },
    ],
  },
  {
    heading: "Reporting",
    items: [
      { href: "/reports", label: "Monthly pack", blurb: "Generate, write the commentary, sign, export.", icon: "reports" },
    ],
  },
  {
    heading: "Data",
    items: [
      { href: "/upload", label: "Upload", blurb: "Chart of accounts, trial balance, general ledger, bank and operating files.", icon: "upload" },
      { href: "/load-runs", label: "Load runs", blurb: "Every file received and what happened to it.", icon: "loadRuns" },
      { href: "/mapping", label: "Mapping review", blurb: "Map the ledger to canonical classes, largest rupee value first.", icon: "mapping" },
    ],
  },
  {
    heading: "Assurance",
    items: [
      { href: "/data-health", label: "Data health", blurb: "Freshness, completeness, reconciliation, open exceptions.", icon: "dataHealth" },
      { href: "/exceptions", label: "Exceptions", blurb: "What is blocking output, sorted by money at stake.", icon: "exceptions" },
    ],
  },
];

export const SETTINGS_ITEM: NavItem = {
  href: "/settings",
  label: "Settings",
  blurb: "Roles, employee access grants, audit log.",
  icon: "settings",
};

/** corpus/02 section 2: the promoter's three screens. */
const PROMOTER_HREFS = new Set(["/overview", "/ask", "/reports"]);

export function visibleGroups(role: string | null | undefined): NavGroup[] {
  // An unrecognised or absent role is not treated as a restriction -- the
  // backend still gates every call, and a user staring at an empty sidebar
  // has no way to tell a permissions model from a broken deployment.
  if (role !== "promoter") return NAV_GROUPS;
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => PROMOTER_HREFS.has(item.href)),
  })).filter((group) => group.items.length > 0);
}

export function showsSettings(role: string | null | undefined): boolean {
  return role !== "promoter";
}
