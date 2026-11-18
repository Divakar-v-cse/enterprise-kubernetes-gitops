import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Overview } from "./pages/ops/Overview";
import { Cluster } from "./pages/ops/Cluster";
import { Namespaces } from "./pages/ops/Namespaces";
import { Workloads } from "./pages/ops/Workloads";
import { Deployments } from "./pages/ops/Deployments";
import { Pods } from "./pages/ops/Pods";
import { Services } from "./pages/ops/Services";
import { GitOps } from "./pages/ops/GitOps";
import { Monitoring } from "./pages/ops/Monitoring";
import { Logs } from "./pages/ops/Logs";
import { Alerts } from "./pages/ops/Alerts";
import { Security } from "./pages/ops/Security";
import { History } from "./pages/ops/History";
import { Settings } from "./pages/ops/Settings";
import { Storefront } from "./pages/Storefront";
import { NotFound } from "./pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/ops" replace />} />
      <Route path="/ops" element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="cluster" element={<Cluster />} />
        <Route path="namespaces" element={<Namespaces />} />
        <Route path="workloads" element={<Workloads />} />
        <Route path="deployments" element={<Deployments />} />
        <Route path="pods" element={<Pods />} />
        <Route path="services" element={<Services />} />
        <Route path="gitops" element={<GitOps />} />
        <Route path="monitoring" element={<Monitoring />} />
        <Route path="logs" element={<Logs />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="security" element={<Security />} />
        <Route path="history" element={<History />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="/store" element={<Storefront />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
