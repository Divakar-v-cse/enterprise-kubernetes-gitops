import { Link } from "react-router-dom";
import { useSettings } from "../lib/settings";

interface TopbarProps {
  title: string;
  subtitle?: string;
  onToggleNav: () => void;
  navOpen: boolean;
}

export function Topbar({ title, subtitle, onToggleNav, navOpen }: TopbarProps) {
  const { config } = useSettings();
  const docsUrl = `${config.apiBase.replace(/\/+$/, "")}/api/docs`;

  return (
    <header className="topbar">
      <button
        type="button"
        className="topbar__nav-toggle"
        onClick={onToggleNav}
        aria-expanded={navOpen}
        aria-controls="sidebar"
        aria-label={navOpen ? "Close navigation" : "Open navigation"}
      >
        <span aria-hidden="true">☰</span>
      </button>
      <div className="topbar__heading">
        <h1 className="topbar__title">{title}</h1>
        {subtitle ? <p className="topbar__subtitle">{subtitle}</p> : null}
      </div>
      <div className="topbar__actions">
        <span className="topbar__endpoint" title={config.apiBase}>
          <span className="topbar__endpoint-label">API</span>
          <code>{config.apiBase.replace(/^https?:\/\//, "")}</code>
        </span>
        <a className="button button--ghost button--sm" href={docsUrl} target="_blank" rel="noreferrer">
          API docs
        </a>
        <Link className="button button--ghost button--sm" to="/store">
          Storefront
        </Link>
      </div>
    </header>
  );
}
