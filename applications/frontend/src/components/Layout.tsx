import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar, findNavItem } from "./Sidebar";
import { Topbar } from "./Topbar";

const PAGE_SUBTITLES: Record<string, string> = {
  "/ops": "Snapshot of cluster capacity, workload health and GitOps delivery state",
  "/ops/cluster": "Node inventory, capacity and resource pressure",
  "/ops/namespaces": "Namespace inventory with pod distribution and labels",
  "/ops/workloads": "Deployments, StatefulSets and DaemonSets across namespaces",
  "/ops/deployments": "Rollout status, replica readiness and container images",
  "/ops/pods": "Pod phases, restart counts and per-container detail",
  "/ops/services": "Service discovery, cluster IPs and exposed ports",
  "/ops/gitops": "Argo CD application sync and health state",
  "/ops/history": "Derived from Argo CD application status",
  "/ops/monitoring": "CPU, memory, throughput and latency from /api/metrics",
  "/ops/logs": "Structured log entries with namespace, pod and level filters",
  "/ops/alerts": "Firing and resolved alert rules with runbooks",
  "/ops/security": "Scanner findings by severity with remediation guidance",
  "/ops/settings": "API endpoint, bearer token and connection diagnostics",
};

export function Layout() {
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  const navItem = findNavItem(location.pathname);
  const title = navItem?.label ?? "Ops";
  const subtitle = PAGE_SUBTITLES[location.pathname];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />
      {navOpen ? (
        <button
          type="button"
          className="sidebar__scrim"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      ) : null}
      <div className="app-main">
        <Topbar title={title} subtitle={subtitle} onToggleNav={() => setNavOpen((open) => !open)} navOpen={navOpen} />
        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>Read-only control plane · demo data is always labelled</span>
          <span>Platform API &amp; API Gateway</span>
        </footer>
      </div>
    </div>
  );
}
