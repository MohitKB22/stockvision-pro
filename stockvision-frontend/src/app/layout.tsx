import type { Metadata, Viewport } from "next";

import { AppProviders } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "StockVision Pro — AI Market Analytics",
    template: "%s · StockVision Pro",
  },
  description:
    "AI-powered stock market analytics: live market intelligence, portfolio and risk analytics, ML price prediction and a RAG copilot over financial documents.",
  applicationName: "StockVision Pro",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#070b12",
  width: "device-width",
  initialScale: 1,
  // Not locked to 1: capping user zoom is an accessibility failure, and it is the
  // default in most "app-like" viewport snippets people copy.
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="min-h-dvh bg-canvas font-sans text-ink antialiased">
        {/* First tab stop on every page — keyboard users should not have to traverse
            the entire sidebar to reach the content. */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
        >
          Skip to content
        </a>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
