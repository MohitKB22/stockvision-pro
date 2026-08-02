"use client";

import * as React from "react";

import { formatPercent } from "@/lib/format";
import { clamp, cn } from "@/lib/utils";
import type { HeatmapEntry } from "@/types";

import { Tooltip } from "../ui/misc";

/**
 * Sector treemap.
 *
 * A real squarified treemap layout, not a grid of equal boxes: tile AREA is
 * proportional to market cap, which is the whole point — a heatmap where a
 * ₹5,000 Cr company occupies the same area as a ₹19 lakh Cr one tells you nothing
 * about where the market actually moved.
 *
 * Implemented directly because Recharts' Treemap does not support the nested
 * sector-then-constituent grouping this needs, and its label handling at small
 * tile sizes is unusable.
 */

interface Tile {
  entry: HeatmapEntry;
  x: number;
  y: number;
  width: number;
  height: number;
}

function squarify(entries: HeatmapEntry[], width: number, height: number): Tile[] {
  const items = [...entries].sort((a, b) => b.market_cap - a.market_cap);
  let remainingValue = items.reduce((sum, e) => sum + Math.max(e.market_cap, 1), 0);
  if (!remainingValue || !items.length) return [];

  const tiles: Tile[] = [];
  let x = 0;
  let y = 0;
  let remainingWidth = width;
  let remainingHeight = height;
  let index = 0;

  while (index < items.length) {
    const horizontal = remainingWidth >= remainingHeight;
    const shortSide = horizontal ? remainingHeight : remainingWidth;

    // Accumulate a row while the worst aspect ratio keeps improving.
    let rowValue = 0;
    let rowCount = 0;
    let bestRatio = Infinity;

    while (index + rowCount < items.length) {
      const candidateValue = rowValue + Math.max(items[index + rowCount].market_cap, 1);
      const area = (candidateValue / remainingValue) * remainingWidth * remainingHeight;
      const thickness = area / shortSide || 1;
      const worst = Math.max(
        ...items.slice(index, index + rowCount + 1).map((item) => {
          const itemArea = (Math.max(item.market_cap, 1) / candidateValue) * area;
          const itemSide = itemArea / thickness || 1;
          return Math.max(thickness / itemSide, itemSide / thickness);
        }),
      );
      if (worst > bestRatio && rowCount > 0) break;
      bestRatio = worst;
      rowValue = candidateValue;
      rowCount += 1;
    }

    const area = (rowValue / remainingValue) * remainingWidth * remainingHeight;
    const thickness = area / shortSide || 1;
    let offset = 0;

    for (let i = 0; i < rowCount; i += 1) {
      const item = items[index + i];
      const itemArea = (Math.max(item.market_cap, 1) / rowValue) * area;
      const itemSide = itemArea / thickness || 1;
      tiles.push({
        entry: item,
        x: horizontal ? x : x + offset,
        y: horizontal ? y + offset : y,
        width: horizontal ? thickness : itemSide,
        height: horizontal ? itemSide : thickness,
      });
      offset += itemSide;
    }

    if (horizontal) {
      x += thickness;
      remainingWidth -= thickness;
    } else {
      y += thickness;
      remainingHeight -= thickness;
    }
    remainingValue -= rowValue;
    index += rowCount;
    if (remainingWidth <= 0.5 || remainingHeight <= 0.5) break;
  }

  return tiles;
}

/** Change % -> background. Lightness carries the magnitude, so the map stays
 *  readable in greyscale and for red/green colour-vision deficiency. */
function tileColor(changePct: number): string {
  if (Math.abs(changePct) < 0.0005) return "hsl(var(--line) / 0.85)";
  const intensity = clamp(Math.abs(changePct) / 0.04, 0.12, 1);
  return changePct > 0
    ? `hsl(158 74% ${28 + intensity * 18}% / ${0.35 + intensity * 0.5})`
    : `hsl(0 74% ${34 + intensity * 16}% / ${0.35 + intensity * 0.5})`;
}

export function SectorHeatmap({
  entries,
  height = 380,
  onSelect,
}: {
  entries: HeatmapEntry[];
  height?: number;
  onSelect?: (symbol: string) => void;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(900);

  React.useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const groups = React.useMemo(() => {
    const bySector = new Map<string, HeatmapEntry[]>();
    for (const entry of entries) {
      const list = bySector.get(entry.sector) ?? [];
      list.push(entry);
      bySector.set(entry.sector, list);
    }
    return [...bySector.entries()]
      .map(([sector, items]) => ({
        sector,
        items,
        marketCap: items.reduce((sum, item) => sum + item.market_cap, 0),
      }))
      .sort((a, b) => b.marketCap - a.marketCap);
  }, [entries]);

  if (!entries.length) {
    return (
      <div className="flex items-center justify-center text-xs text-ink-faint" style={{ height }}>
        No heatmap data available
      </div>
    );
  }

  const totalCap = groups.reduce((sum, group) => sum + group.marketCap, 0) || 1;

  return (
    <div ref={containerRef} className="space-y-2">
      {groups.map((group) => {
        const groupHeight = Math.max(72, (group.marketCap / totalCap) * height * 1.6);
        const tiles = squarify(group.items, width, groupHeight);
        return (
          <div key={group.sector}>
            <p className="mb-1 text-2xs font-semibold uppercase tracking-wider text-ink-faint">
              {group.sector}
            </p>
            <div className="relative w-full" style={{ height: groupHeight }}>
              {tiles.map((tile) => {
                const showLabel = tile.width > 54 && tile.height > 30;
                return (
                  <Tooltip
                    key={tile.entry.symbol}
                    content={
                      <div className="space-y-0.5">
                        <p className="font-medium text-ink">{tile.entry.name}</p>
                        <p className="text-ink-subtle">
                          {tile.entry.symbol} · {formatPercent(tile.entry.change_pct)}
                        </p>
                      </div>
                    }
                  >
                    <button
                      type="button"
                      onClick={() => onSelect?.(tile.entry.symbol)}
                      className={cn(
                        "absolute overflow-hidden rounded-md border border-canvas/60 p-1.5 text-left transition-all duration-200 ease-smooth",
                        "hover:z-10 hover:scale-[1.02] hover:border-ink/25 focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-primary",
                      )}
                      style={{
                        left: tile.x,
                        top: tile.y,
                        width: Math.max(tile.width - 2, 2),
                        height: Math.max(tile.height - 2, 2),
                        backgroundColor: tileColor(tile.entry.change_pct),
                      }}
                      aria-label={`${tile.entry.symbol}, ${formatPercent(tile.entry.change_pct)}`}
                    >
                      {showLabel ? (
                        <>
                          <span className="block truncate text-2xs font-semibold text-ink">
                            {tile.entry.symbol}
                          </span>
                          <span className="tabular block text-2xs text-ink/80">
                            {formatPercent(tile.entry.change_pct, { decimals: 1 })}
                          </span>
                        </>
                      ) : null}
                    </button>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
