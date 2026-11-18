import { Fragment } from "react";
import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
}

export interface ExpandConfig<T> {
  isExpanded: (row: T) => boolean;
  onToggle: (row: T) => void;
  render: (row: T) => ReactNode;
  label?: (row: T) => string;
}

interface DataTableProps<T> {
  columns: Array<Column<T>>;
  rows: T[];
  rowKey: (row: T) => string;
  caption?: string;
  dense?: boolean;
  expand?: ExpandConfig<T>;
}

/** Accessible table with real <thead>/<th scope="col"> headers. */
export function DataTable<T>({ columns, rows, rowKey, caption, dense, expand }: DataTableProps<T>) {
  const columnCount = columns.length + (expand ? 1 : 0);
  return (
    <div className="table-wrap">
      <table className={`data-table${dense ? " data-table--dense" : ""}`}>
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {expand ? <th scope="col" className="data-table__expand-head"><span className="sr-only">Expand</span></th> : null}
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.className}
                style={column.align ? { textAlign: column.align } : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            const expanded = expand ? expand.isExpanded(row) : false;
            return (
              <Fragment key={key}>
                <tr className={expanded ? "is-expanded" : undefined}>
                  {expand ? (
                    <td className="data-table__expand-cell">
                      <button
                        type="button"
                        className="icon-button"
                        aria-expanded={expanded}
                        aria-label={`${expanded ? "Collapse" : "Expand"} details for ${expand.label ? expand.label(row) : key}`}
                        onClick={() => expand.onToggle(row)}
                      >
                        <span aria-hidden="true">{expanded ? "−" : "+"}</span>
                      </button>
                    </td>
                  ) : null}
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={column.className}
                      style={column.align ? { textAlign: column.align } : undefined}
                    >
                      {column.render ? column.render(row) : String((row as Record<string, unknown>)[column.key] ?? "—")}
                    </td>
                  ))}
                </tr>
                {expand && expanded ? (
                  <tr className="data-table__expanded-row">
                    <td colSpan={columnCount}>{expand.render(row)}</td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
