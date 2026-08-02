import { cn } from "@/lib/utils";

/** Consistent page heading + action slot. Every page uses this, so headings cannot
 *  drift in size, spacing or hierarchy from one route to the next. */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        <h2 className="text-xl font-semibold tracking-tight text-ink">{title}</h2>
        {description ? <p className="mt-1 text-xs text-ink-subtle">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
