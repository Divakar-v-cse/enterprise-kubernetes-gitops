interface LoadingProps {
  label?: string;
  rows?: number;
}

/** Skeleton placeholder — matches table/card silhouette so layout stays stable. */
export function Loading({ label = "Loading data", rows = 6 }: LoadingProps) {
  return (
    <div className="skeleton" role="status" aria-live="polite" aria-label={label}>
      <div className="skeleton__row skeleton__row--head">
        {Array.from({ length: 4 }).map((_, index) => (
          <span key={index} className="skeleton__block" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, index) => (
        <div className="skeleton__row" key={index}>
          {Array.from({ length: 4 }).map((__, cell) => (
            <span key={cell} className="skeleton__block" style={{ width: `${60 - cell * 8}%` }} />
          ))}
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}
