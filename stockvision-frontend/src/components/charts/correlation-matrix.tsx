"use client";

import { clamp } from "@/lib/utils";

import { Tooltip } from "../ui/misc";

/**
 * Correlation heatmap.
 *
 * Diverging blue-to-red scale centred at zero, because correlation is a SIGNED
 * quantity and a sequential (single-hue) scale makes -0.9 and +0.9 look similar —
 * the single most misleading thing you can do to a correlation matrix.
 */
export function CorrelationMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  if (!labels.length || !matrix.length) {
    return (
      <p className="py-8 text-center text-xs text-ink-faint">
        At least two holdings with overlapping price history are needed to compute correlations.
      </p>
    );
  }

  const cellColor = (value: number) => {
    const intensity = clamp(Math.abs(value), 0.05, 1);
    return value >= 0
      ? `hsl(0 74% 55% / ${intensity * 0.75})`
      : `hsl(217 91% 60% / ${intensity * 0.75})`;
  };

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0.5">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-surface px-1" />
            {labels.map((label) => (
              <th
                key={label}
                className="h-16 w-10 align-bottom text-2xs font-medium text-ink-subtle"
              >
                <span className="inline-block origin-bottom-left translate-x-3 -rotate-45 whitespace-nowrap">
                  {label}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, rowIndex) => (
            <tr key={labels[rowIndex]}>
              <th className="sticky left-0 z-10 bg-surface pr-2 text-right text-2xs font-medium text-ink-subtle">
                {labels[rowIndex]}
              </th>
              {row.map((value, colIndex) => (
                <td key={`${rowIndex}-${colIndex}`}>
                  <Tooltip
                    content={`${labels[rowIndex]} / ${labels[colIndex]}: ${value.toFixed(3)}`}
                  >
                    <div
                      className="tabular grid size-10 cursor-default place-items-center rounded-md text-2xs font-medium text-ink transition-transform hover:scale-110"
                      style={{
                        backgroundColor:
                          rowIndex === colIndex ? "hsl(var(--line-strong))" : cellColor(value),
                      }}
                    >
                      {value.toFixed(2)}
                    </div>
                  </Tooltip>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 flex items-center gap-3 text-2xs text-ink-faint">
        <span>−1 (inverse)</span>
        <div
          className="h-1.5 w-32 rounded-full"
          style={{
            background:
              "linear-gradient(90deg, hsl(217 91% 60% / 0.75), hsl(var(--line-strong)), hsl(0 74% 55% / 0.75))",
          }}
          aria-hidden
        />
        <span>+1 (moves together)</span>
      </div>
    </div>
  );
}
