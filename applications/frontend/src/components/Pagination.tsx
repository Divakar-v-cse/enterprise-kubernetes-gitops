interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
  label?: string;
}

/** Offset pagination driven by the meta block returned from platform-api. */
export function Pagination({ total, limit, offset, onChange, label = "rows" }: PaginationProps) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="pagination__summary">
        {from}–{to} of {total} {label}
      </span>
      <div className="pagination__buttons">
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={() => onChange(Math.max(0, offset - limit))}
          disabled={!canPrev}
          aria-label="Previous page"
        >
          Previous
        </button>
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={() => onChange(offset + limit)}
          disabled={!canNext}
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </nav>
  );
}
