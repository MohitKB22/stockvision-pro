import Link from "next/link";
import { Compass } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="grid min-h-dvh place-items-center px-6">
      <div className="text-center">
        <div className="mx-auto mb-5 grid size-14 place-items-center rounded-2xl border border-line bg-elevated">
          <Compass className="size-6 text-ink-subtle" aria-hidden />
        </div>
        <p className="font-mono text-2xs uppercase tracking-widest text-primary">Error 404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Page not found</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm text-ink-subtle">
          That route does not exist in this application. It may have been renamed or removed.
        </p>
        <Button variant="primary" className="mt-6" asChild>
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
