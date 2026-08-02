import {
  Activity,
  BarChart3,
  FileText,
  Gauge,
  LayoutDashboard,
  Newspaper,
  Settings,
  ShieldAlert,
  Star,
  Wallet,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  description: string;
  group: "Overview" | "Analytics" | "Intelligence" | "Platform";
  mobile?: boolean;
}

/**
 * The single source of navigation truth.
 *
 * Sidebar, mobile bar, command palette and page headings all read from here, so a
 * new page cannot appear in one navigation surface and be missing from another —
 * which is how "dummy navigation" and dead links happen.
 */
export const NAV_ITEMS: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    description: "Portfolio, market and AI signals at a glance",
    group: "Overview",
    mobile: true,
  },
  {
    href: "/market",
    label: "Market",
    icon: BarChart3,
    description: "Indices, movers, sectors, heatmap and breadth",
    group: "Overview",
    mobile: true,
  },
  {
    href: "/watchlist",
    label: "Watchlist",
    icon: Star,
    description: "Tracked symbols with price alerts",
    group: "Overview",
  },
  {
    href: "/news",
    label: "News",
    icon: Newspaper,
    description: "Headlines with sentiment scoring",
    group: "Overview",
  },

  {
    href: "/portfolio",
    label: "Portfolio",
    icon: Wallet,
    description: "Holdings, allocation, transactions and performance",
    group: "Analytics",
    mobile: true,
  },
  {
    href: "/risk",
    label: "Risk Analytics",
    icon: ShieldAlert,
    description: "VaR, Monte Carlo, correlation and stress tests",
    group: "Analytics",
  },
  {
    href: "/reports",
    label: "Reports",
    icon: FileText,
    description: "Generate and export PDF, CSV and Excel reports",
    group: "Analytics",
  },

  {
    href: "/prediction",
    label: "AI Prediction",
    icon: Activity,
    description: "Forecasts, model registry and SHAP explanations",
    group: "Intelligence",
    mobile: true,
  },

  {
    href: "/admin",
    label: "Admin",
    icon: Gauge,
    description: "Usage analytics, system health and audit log",
    group: "Platform",
  },
  {
    href: "/settings",
    label: "Settings",
    icon: Settings,
    description: "Preferences, integrations and appearance",
    group: "Platform",
  },
];

export const NAV_GROUPS = ["Overview", "Analytics", "Intelligence", "Platform"] as const;

export const MOBILE_NAV_ITEMS = NAV_ITEMS.filter((item) => item.mobile);

export function navItemForPath(pathname: string): NavItem | undefined {
  return (
    NAV_ITEMS.find((item) => item.href === pathname) ??
    NAV_ITEMS.find((item) => pathname.startsWith(`${item.href}/`))
  );
}
