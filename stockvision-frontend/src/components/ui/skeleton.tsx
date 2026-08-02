import { cn } from "@/lib/utils";

/**
 * Loading placeholder.
 *
 * Skeletons must match the SHAPE of the content they stand in for. A generic grey
 * box that resolves into a different layout causes a visible reflow — the thing
 * skeletons exist to prevent — so the composed variants below mirror the real
 * components' dimensions.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("skeleton", className)} aria-hidden {...props} />;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} className={cn("h-3", index === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export function SkeletonStatCard() {
  return (
    <div className="glass rounded-2xl p-5">
      <Skeleton className="h-2.5 w-24" />
      <Skeleton className="mt-3 h-7 w-36" />
      <Skeleton className="mt-3 h-3 w-20" />
    </div>
  );
}

export function SkeletonChart({ className }: { className?: string }) {
  return (
    <div className={cn("glass flex flex-col gap-3 rounded-2xl p-5", className)}>
      <Skeleton className="h-3 w-32" />
      <Skeleton className="h-[220px] w-full rounded-xl" />
    </div>
  );
}

export function SkeletonTable({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="space-y-2">
      <div className="flex gap-3">
        {Array.from({ length: columns }).map((_, index) => (
          <Skeleton key={index} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Skeleton key={colIndex} className="h-8 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
