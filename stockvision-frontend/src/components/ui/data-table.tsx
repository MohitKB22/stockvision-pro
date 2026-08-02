"use client";

import * as React from "react";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";

import { cn } from "@/lib/utils";

import { Button } from "./button";
import { EmptyState } from "./states";

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  emptyTitle?: string;
  emptyDescription?: string;
  pageSize?: number;
  onRowClick?: (row: TData) => void;
  className?: string;
  dense?: boolean;
}

/**
 * TanStack Table wrapper.
 *
 * Sorting, filtering and pagination are all client-side, which is the correct
 * trade-off for these datasets: the API caps every list endpoint at 500 rows, so
 * the entire result is already in memory and a server round-trip per sort click
 * would be strictly slower and less responsive.
 */
export function DataTable<TData, TValue>({
  columns,
  data,
  emptyTitle = "No records",
  emptyDescription,
  pageSize = 12,
  onRowClick,
  className,
  dense = false,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  if (!data.length) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  const showPagination = table.getPageCount() > 1;

  return (
    <div className={cn("w-full", className)}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-full border-collapse text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-line">
                {headerGroup.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      className={cn(
                        "whitespace-nowrap px-3 py-2 text-left text-2xs font-semibold uppercase tracking-wider text-ink-faint",
                        canSort &&
                          "cursor-pointer select-none transition-colors hover:text-ink-muted",
                      )}
                      onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                      aria-sort={
                        sorted === "asc"
                          ? "ascending"
                          : sorted === "desc"
                            ? "descending"
                            : undefined
                      }
                    >
                      <span className="inline-flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {canSort ? (
                          sorted === "asc" ? (
                            <ArrowUp className="size-3 text-primary" aria-hidden />
                          ) : sorted === "desc" ? (
                            <ArrowDown className="size-3 text-primary" aria-hidden />
                          ) : (
                            <ChevronsUpDown className="size-3 opacity-40" aria-hidden />
                          )
                        ) : null}
                      </span>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={cn(
                  "border-b border-line/50 transition-colors last:border-0",
                  onRowClick && "cursor-pointer hover:bg-elevated/70",
                )}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className={cn("px-3", dense ? "py-1.5" : "py-2.5")}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showPagination ? (
        <div className="flex items-center justify-between border-t border-line px-3 py-2.5">
          <p className="text-2xs text-ink-faint">
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()} ·{" "}
            {data.length} rows
          </p>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              aria-label="Previous page"
            >
              <ChevronLeft aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              aria-label="Next page"
            >
              <ChevronRight aria-hidden />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
