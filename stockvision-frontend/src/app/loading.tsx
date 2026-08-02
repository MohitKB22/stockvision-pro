import { SkeletonChart, SkeletonStatCard } from "@/components/ui/skeleton";

/** Route-transition fallback. Mirrors the dashboard's grid so the shift into real
 *  content is a fill, not a reflow. */
export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="skeleton h-7 w-56 rounded-lg" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonStatCard key={index} />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <SkeletonChart className="lg:col-span-2" />
        <SkeletonChart />
      </div>
    </div>
  );
}
