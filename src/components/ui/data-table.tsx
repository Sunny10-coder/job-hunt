import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/format";
import { EmptyState } from "./primitives";

export function DataTable<T>({
  columns,
  data,
  onRowClick,
  empty = "No records",
  initialSort = [],
  maxHeight,
  className,
  rowKey,
}: {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  onRowClick?: (row: T) => void;
  empty?: React.ReactNode;
  initialSort?: SortingState;
  maxHeight?: number | string;
  className?: string;
  rowKey?: (row: T, index: number) => string;
}) {
  const [sorting, setSorting] = React.useState<SortingState>(initialSort);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div
      className={cn("overflow-auto scroll-thin", className)}
      style={{ maxHeight: maxHeight ?? "100%" }}
    >
      <table className="data-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const sortable = header.column.getCanSort();
                return (
                  <th
                    key={header.id}
                    style={{ width: header.getSize() === 150 ? undefined : header.getSize() }}
                    onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                    className={cn(sortable && "cursor-pointer select-none hover:text-ink")}
                  >
                    <span className="inline-flex items-center gap-1">
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc" ? (
                        <ArrowUp className="h-3 w-3" />
                      ) : header.column.getIsSorted() === "desc" ? (
                        <ArrowDown className="h-3 w-3" />
                      ) : null}
                    </span>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="border-none">
                <EmptyState title={typeof empty === "string" ? empty : "No records"} />
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row, index) => (
              <tr
                key={rowKey ? rowKey(row.original, index) : row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={cn(onRowClick && "cursor-pointer")}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
