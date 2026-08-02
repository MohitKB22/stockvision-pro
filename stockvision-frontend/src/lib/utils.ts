import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind classes with correct conflict resolution.
 *
 * `clsx` handles conditionals; `twMerge` resolves conflicts so a caller can
 * override a component's base class (`<Button className="px-8">` genuinely wins
 * over the variant's `px-4`) instead of both landing in the class list and the
 * outcome depending on stylesheet order.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Clamp with NaN safety — a NaN from a divide-by-zero would otherwise propagate
 *  silently into a chart axis or a CSS width. */
export function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(Math.max(value, min), max);
}
