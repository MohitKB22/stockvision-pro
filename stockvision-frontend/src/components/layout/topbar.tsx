"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Bell, Menu, TrendingUp, X } from "lucide-react";

import { useMarket } from "@/context/market-context";
import { get } from "@/lib/api";
import { NAV_ITEMS, navItemForPath } from "@/lib/navigation";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import type { SessionStatus } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { DemoBadge } from "./demo-badge";
import { MarketSwitcher } from "./market-switcher";
import { SearchCommand } from "./search-command";

function SessionBadge() {
  const { market } = useMarket();
  const { data } = useQuery({
    queryKey: queryKeys.session(market),
    queryFn: () => get<SessionStatus>("/market/session", { market }),
    // A minute is plenty: the open/close boundary is the only thing that changes,
    // and polling harder just adds requests for no information.
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (!data) return null;

  return (
    <Badge variant={data.is_open ? "gain" : "default"} className="hidden gap-1.5 sm:inline-flex">
      <span
        className={cn(
          "size-1.5 rounded-full",
          data.is_open ? "animate-pulse bg-gain" : "bg-ink-faint",
        )}
        aria-hidden
      />
      {data.is_open ? "Market open" : "Market closed"}
    </Badge>
  );
}

export function Topbar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const current = navItemForPath(pathname);

  return (
    <>
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-canvas/80 px-4 backdrop-blur-xl lg:px-6">
        <Button
          variant="ghost"
          size="icon-sm"
          className="lg:hidden"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation menu"
        >
          <Menu aria-hidden />
        </Button>

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-sm font-semibold tracking-tight text-ink">
            {current?.label ?? "StockVision Pro"}
          </h1>
          <p className="hidden truncate text-2xs text-ink-faint sm:block">
            {current?.description ?? "AI-powered market analytics"}
          </p>
        </div>

        <DemoBadge />
        <SessionBadge />
        <SearchCommand />
        <MarketSwitcher compact />

        <Button variant="ghost" size="icon-sm" aria-label="Notifications" asChild>
          <Link href="/news">
            <Bell aria-hidden />
          </Link>
        </Button>
      </header>

      {/* Mobile drawer. Rendered outside the header so it can cover the full
          viewport, and gated on state so its links are not in the tab order while
          it is closed. The drawer closes in each link's own onClick rather than in
          an effect watching `pathname` — reacting to the route change means an
          extra render pass after navigation (and React 19's compiler flags it);
          closing on the interaction that causes the navigation is simpler and
          immediate. */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-canvas/85 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation menu"
          />
          <nav className="glass-strong absolute inset-y-0 left-0 flex w-[264px] animate-fade-up flex-col">
            <div className="flex h-14 items-center justify-between border-b border-line px-4">
              <span className="flex items-center gap-2.5">
                <span className="grid size-8 place-items-center rounded-lg bg-gradient-primary">
                  <TrendingUp className="size-4 text-white" aria-hidden />
                </span>
                <span className="text-sm font-semibold text-ink">StockVision Pro</span>
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setMobileOpen(false)}
                aria-label="Close"
              >
                <X aria-hidden />
              </Button>
            </div>
            <ul className="flex-1 space-y-0.5 overflow-y-auto p-3">
              {NAV_ITEMS.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      onClick={() => setMobileOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                        active
                          ? "bg-primary/12 font-medium text-primary"
                          : "text-ink-muted hover:bg-elevated",
                      )}
                    >
                      <Icon className="size-4 shrink-0" aria-hidden />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
            <div className="border-t border-line p-3">
              <MarketSwitcher />
            </div>
          </nav>
        </div>
      ) : null}
    </>
  );
}
