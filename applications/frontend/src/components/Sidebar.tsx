import { NavLink } from "react-router-dom";

export interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Platform",
    items: [
      { to: "/ops", label: "Platform Overview", icon: "◎", end: true },
      { to: "/ops/cluster", label: "Cluster", icon: "▤" },
      { to: "/ops/namespaces", label: "Namespaces", icon: "▥" },
    ],
  },
  {
    label: "Workloads",
    items: [
      { to: "/ops/workloads", label: "Workloads", icon: "▦" },
      { to: "/ops/deployments", label: "Deployments", icon: "⇪" },
      { to: "/ops/pods", label: "Pods", icon: "◍" },
      { to: "/ops/services", label: "Services", icon: "⇄" },
    ],
  },
  {
    label: "Delivery",
    items: [
      { to: "/ops/gitops", label: "GitOps", icon: "⑃" },
      { to: "/ops/history", label: "Deployment History", icon: "⟲" },
    ],
  },
  {
    label: "Observability",
    items: [
      { to: "/ops/monitoring", label: "Monitoring", icon: "◔" },
      { to: "/ops/logs", label: "Logs", icon: "≡" },
      { to: "/ops/alerts", label: "Alerts", icon: "⚑" },
    ],
  },
  {
    label: "Governance",
    items: [
      { to: "/ops/security", label: "Security", icon: "⛨" },
      { to: "/ops/settings", label: "Settings", icon: "⚙" },
    ],
  },
];

export function findNavItem(pathname: string): NavItem | undefined {
  const all = NAV_GROUPS.flatMap((group) => group.items);
  return all.find((item) => item.to === pathname) ?? all.find((item) => item.to !== "/ops" && pathname.startsWith(item.to));
}

interface SidebarProps {
  open: boolean;
  onNavigate: () => void;
}

export function Sidebar({ open, onNavigate }: SidebarProps) {
  return (
    <aside id="sidebar" className={`sidebar${open ? " sidebar--open" : ""}`} aria-label="Ops dashboard navigation">
      <div className="sidebar__brand">
        <span className="sidebar__logo" aria-hidden="true">K8</span>
        <div>
          <div className="sidebar__name">GitOps Platform</div>
          <div className="sidebar__tag">control plane</div>
        </div>
      </div>

      <nav className="sidebar__nav" aria-label="Ops sections">
        {NAV_GROUPS.map((group) => (
          <div className="sidebar__group" key={group.label}>
            <div className="sidebar__group-label">{group.label}</div>
            <ul className="sidebar__list">
              {group.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={onNavigate}
                    className={({ isActive }) => `sidebar__link${isActive ? " is-active" : ""}`}
                  >
                    <span className="sidebar__icon" aria-hidden="true">{item.icon}</span>
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="sidebar__footer">
        <NavLink to="/store" className="sidebar__store" onClick={onNavigate}>
          <span aria-hidden="true">◈</span>
          <span>
            Storefront demo
            <small>microservices + gateway</small>
          </span>
        </NavLink>
        <p className="sidebar__note">Read-only platform API</p>
      </div>
    </aside>
  );
}
