interface EmptyStateProps {
  title: string;
  message?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, message, action }: EmptyStateProps) {
  return (
    <div className="state state--empty" role="status">
      <div className="state__icon" aria-hidden="true">∅</div>
      <h3 className="state__title">{title}</h3>
      {message ? <p className="state__message">{message}</p> : null}
      {action ? <div className="state__action">{action}</div> : null}
    </div>
  );
}
