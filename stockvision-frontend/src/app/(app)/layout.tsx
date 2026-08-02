import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";

/**
 * The application shell.
 *
 * A route group `(app)` rather than a path segment, so every page keeps its clean
 * URL (`/dashboard`, not `/app/dashboard`) while sharing this chrome.
 *
 * `lg:pl-[248px]` matches the sidebar's expanded width. It is intentionally NOT
 * driven by the sidebar's collapsed state: threading that through a context would
 * re-render every page on a purely visual toggle. The sidebar overlays within its
 * own fixed track instead.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-dvh">
      {/* Ambient background: a subtle grid plus a top glow. Fixed and
          pointer-events-none so it never intercepts clicks or scrolls. */}
      <div className="pointer-events-none fixed inset-0 bg-grid opacity-[0.35]" aria-hidden />
      <div
        className="pointer-events-none fixed inset-x-0 top-0 h-[420px] bg-gradient-glow"
        aria-hidden
      />

      <Sidebar />

      <div className="relative lg:pl-[248px]">
        <Topbar />
        <main
          id="main-content"
          className="mx-auto w-full max-w-[1600px] px-4 pb-24 pt-5 lg:px-6 lg:pb-10"
        >
          {children}
        </main>
      </div>

      <MobileNav />
    </div>
  );
}
