"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen, TrendingUp } from "lucide-react";

import { usePersistentBoolean } from "@/hooks/use-persistent-state";
import { NAV_GROUPS, NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { Tooltip } from "@/components/ui/misc";

import { SystemStatusDot } from "./system-status";

const STORAGE_KEY = "stockvision.sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  // Persisted via useSyncExternalStore — see hooks/use-persistent-state.ts for why
  // this is not `useState` + `useEffect` (cascading render, plus a visible flash of
  // the expanded sidebar before it collapses).
  const [collapsed, setCollapsed] = usePersistentBoolean(STORAGE_KEY, false);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-line bg-surface/85 backdrop-blur-xl transition-[width] duration-300 ease-smooth lg:flex",
        collapsed ? "w-[68px]" : "w-[248px]",
      )}
      aria-label="Primary navigation"
    >
      <div className="flex h-14 items-center gap-2.5 border-b border-line px-4">
        <Link
          href="/dashboard"
          className="flex min-w-0 items-center gap-2.5"
          aria-label="StockVision Pro home"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-gradient-primary shadow-glow">
            <TrendingUp className="size-4 text-white" aria-hidden />
          </span>
          {!collapsed ? (
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold tracking-tight text-ink">
                StockVision
              </span>
              <span className="block text-2xs font-medium tracking-wider text-primary">PRO</span>
            </span>
          ) : null}
        </Link>
      </div>

      <nav className="scrollbar-none flex-1 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => {
          const items = NAV_ITEMS.filter((item) => item.group === group);
          if (!items.length) return null;
          return (
            <div key={group} className="mb-5 last:mb-0">
              {!collapsed ? (
                <p className="mb-1.5 px-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-faint">
                  {group}
                </p>
              ) : (
                <div className="mx-2.5 mb-2 border-t border-line" aria-hidden />
              )}
              <ul className="space-y-0.5">
                {items.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const Icon = item.icon;
                  const link = (
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-all duration-200 ease-smooth",
                        active
                          ? "bg-primary/12 font-medium text-primary"
                          : "text-ink-muted hover:bg-elevated hover:text-ink",
                        collapsed && "justify-center px-0",
                      )}
                    >
                      {active ? (
                        <span
                          className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary"
                          aria-hidden
                        />
                      ) : null}
                      <Icon className="size-4 shrink-0" aria-hidden />
                      {!collapsed ? <span className="truncate">{item.label}</span> : null}
                    </Link>
                  );
                  return (
                    <li key={item.href}>
                      {collapsed ? (
                        <Tooltip side="right" content={item.label}>
                          {link}
                        </Tooltip>
                      ) : (
                        link
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className="border-t border-line p-3">
        <SystemStatusDot collapsed={collapsed} />
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg px-2.5 py-2 text-xs text-ink-subtle transition-colors hover:bg-elevated hover:text-ink"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4" aria-hidden />
          ) : (
            <>
              <PanelLeftClose className="size-4" aria-hidden />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
