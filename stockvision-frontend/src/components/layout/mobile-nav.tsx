"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { MOBILE_NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

/**
 * Bottom tab bar for small screens.
 *
 * Carries `pb-[env(safe-area-inset-bottom)]` so the tabs are not obscured by the
 * home indicator on notched iOS devices — without it the last few pixels of every
 * tab are untappable.
 */
export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
      aria-label="Primary"
    >
      <ul className="flex items-stretch">
        {MOBILE_NAV_ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex flex-col items-center gap-1 py-2.5 text-2xs transition-colors",
                  active ? "text-primary" : "text-ink-faint",
                )}
              >
                <Icon className="size-[18px]" aria-hidden />
                <span className="truncate px-1">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
