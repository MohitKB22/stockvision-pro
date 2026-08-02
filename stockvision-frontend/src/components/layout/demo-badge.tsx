"use client";

import { FlaskConical } from "lucide-react";

import { IS_DEMO } from "@/lib/demo";
import { Badge } from "@/components/ui/badge";

/**
 * Says out loud that the data is not real.
 *
 * The project's stated posture is that anything synthetic is labelled as
 * synthetic in the UI, not only in the README. A deployed demo with no backend
 * is exactly the case where an unlabelled screenshot would mislead someone, so
 * the badge is always visible while demo mode is on - and renders nothing at all
 * when it is off.
 */
export function DemoBadge() {
  if (!IS_DEMO) return null;

  return (
    <Badge
      variant="warn"
      className="hidden gap-1.5 sm:inline-flex"
      title="Demo mode: the FastAPI backend is not connected. Prices are synthetic and generated in your browser; the analytics computed on them are the real calculations."
    >
      <FlaskConical className="size-3" aria-hidden />
      Demo data
    </Badge>
  );
}
