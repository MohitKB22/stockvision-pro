import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide transition-colors",
  {
    variants: {
      variant: {
        default: "border-line-strong bg-elevated text-ink-muted",
        primary: "border-primary/30 bg-primary/12 text-primary",
        accent: "border-accent/30 bg-accent/12 text-accent",
        gain: "border-gain/30 bg-gain/12 text-gain",
        loss: "border-loss/30 bg-loss/12 text-loss",
        warn: "border-warn/30 bg-warn/12 text-warn",
        info: "border-info/30 bg-info/12 text-info",
        outline: "border-line-strong bg-transparent text-ink-subtle",
      },
      size: { sm: "px-1.5 py-0.5 text-2xs", md: "px-2 py-1 text-xs" },
    },
    defaultVariants: { variant: "default", size: "sm" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, size }), className)} {...props} />;
}

export { badgeVariants };
