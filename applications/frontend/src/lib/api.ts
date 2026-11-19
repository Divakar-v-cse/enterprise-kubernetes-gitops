/**
 * Central API client for the GitOps platform dashboard.
 *
 * - Every request goes to an absolute URL taken from the persisted settings
 *   (no dev-server proxy, no hidden fallbacks).
 * - 8s timeout via AbortController.
 * - Failures are normalised into ApiRequestError so pages can render a real
 *   error state instead of invented data.
 */

export type ApiBaseKind = "platform" | "gateway";

export interface RuntimeConfig {
  apiBase: string;
  gatewayBase: string;
  token: string;
  apiKey: string;
}

/**
 * Same-origin deployment detection.
 *
 * When the SPA is served by the in-cluster NGINX ingress it is reachable at
 * :18080 and the API paths are proxied under /platform and /gateway, so
 * relative bases work without any manual configuration. Docker Compose keeps
 * the explicit localhost ports.
 */
function isIngressDeployment(): boolean {
  if (typeof window === "undefined") return false;
  const { port } = window.location;
  return port === "18080" || port === "18443";
}

export const DEFAULT_CONFIG: RuntimeConfig = isIngressDeployment()
  ? {
      apiBase: `${window.location.origin}/platform`,
      gatewayBase: `${window.location.origin}/gateway`,
      token: "platform-demo-token",
      apiKey: "demo-public-key",
    }
  : {
      apiBase: "http://localhost:18081",
      gatewayBase: "http://localhost:18005",
      token: "platform-demo-token",
      apiKey: "demo-public-key",
    };

export const REQUEST_TIMEOUT_MS = 8000;

/* ------------------------------------------------------------------ *
 * Envelope + meta (platform-api `_meta` helper)
 * ------------------------------------------------------------------ */

export type DataSource = "cluster" | "demo" | "security-scan" | (string & {});

export interface Meta {
  source: DataSource;
  cluster?: string;
  generated_at?: string;
  demo_mode?: boolean;
  reason?: string | null;
  count?: number;
  total?: number;
  limit?: number;
  offset?: number;
  /** /api/alerts */
  firing?: number;
  critical?: number;
  /** /api/gitops/status */
  synced?: number;
  out_of_sync?: number;
  degraded?: number;
}

export interface Envelope<T> {
  data: T;
  meta: Meta;
}

/* ------------------------------------------------------------------ *
 * Normalised errors
 * ------------------------------------------------------------------ */

export type ApiErrorKind = "timeout" | "network" | "http" | "parse";

export interface NormalisedError {
  kind: ApiErrorKind;
  status: number | null;
  code: string;
  message: string;
  requestId?: string;
  url: string;
}

export class ApiRequestError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly requestId?: string;
  readonly url: string;

  constructor(detail: NormalisedError) {
    super(detail.message);
    this.name = "ApiRequestError";
    this.kind = detail.kind;
    this.status = detail.status;
    this.code = detail.code;
    this.requestId = detail.requestId;
    this.url = detail.url;
  }

  toJSON(): NormalisedError {
    return {
      kind: this.kind,
      status: this.status,
      code: this.code,
      message: this.message,
      requestId: this.requestId,
      url: this.url,
    };
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; request_id?: string };
  detail?: string;
}

export function normaliseError(error: unknown, url = ""): NormalisedError {
  if (error instanceof ApiRequestError) {
    return error.toJSON();
  }
  if (error instanceof Error) {
    return { kind: "network", status: null, code: "network_error", message: error.message, url };
  }
  return { kind: "network", status: null, code: "unknown_error", message: String(error), url };
}

/* ------------------------------------------------------------------ *
 * Config plumbing (kept module-local; persisted by SettingsProvider)
 * ------------------------------------------------------------------ */

let runtimeConfig: RuntimeConfig = { ...DEFAULT_CONFIG };

export function getRuntimeConfig(): RuntimeConfig {
  return runtimeConfig;
}

export function setRuntimeConfig(next: Partial<RuntimeConfig>): void {
  runtimeConfig = { ...runtimeConfig, ...next };
}

function trimBase(base: string): string {
  return base.replace(/\/+$/, "");
}

export function buildUrl(
  base: ApiBaseKind,
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
): string {
  const root = trimBase(base === "platform" ? runtimeConfig.apiBase : runtimeConfig.gatewayBase);
  const suffix = path.startsWith("/") ? path : `/${path}`;
  const params = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return `${root}${suffix}${qs ? `?${qs}` : ""}`;
}

interface RequestOptions {
  base?: ApiBaseKind;
  method?: "GET" | "POST";
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
  /** Gateway writes need X-API-Key. */
  apiKey?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { base = "platform", method = "GET", query, body, headers, timeoutMs, apiKey } = options;
  const url = buildUrl(base, path, query);
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs ?? REQUEST_TIMEOUT_MS);

  const requestHeaders: Record<string, string> = { Accept: "application/json", ...headers };
  if (body !== undefined) {
    requestHeaders["Content-Type"] = "application/json";
  }
  if (base === "platform" && runtimeConfig.token.trim()) {
    requestHeaders.Authorization = `Bearer ${runtimeConfig.token.trim()}`;
  }
  const needsKey = apiKey ?? (base === "gateway" && method !== "GET");
  if (needsKey && runtimeConfig.apiKey.trim()) {
    requestHeaders["X-API-Key"] = runtimeConfig.apiKey.trim();
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      mode: "cors",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiRequestError({
        kind: "timeout",
        status: null,
        code: "timeout",
        message: `Request timed out after ${(timeoutMs ?? REQUEST_TIMEOUT_MS) / 1000}s`,
        url,
      });
    }
    throw new ApiRequestError({
      kind: "network",
      status: null,
      code: "network_error",
      message:
        error instanceof Error
          ? `Cannot reach ${url} — ${error.message}`
          : `Cannot reach ${url}`,
      url,
    });
  } finally {
    window.clearTimeout(timer);
  }

  if (!response.ok) {
    let parsed: ErrorBody = {};
    try {
      parsed = (await response.json()) as ErrorBody;
    } catch {
      parsed = {};
    }
    throw new ApiRequestError({
      kind: "http",
      status: response.status,
      code: parsed.error?.code ?? `http_${response.status}`,
      message:
        parsed.error?.message ??
        parsed.detail ??
        `${response.status} ${response.statusText || "request failed"}`,
      requestId: parsed.error?.request_id ?? response.headers.get("x-request-id") ?? undefined,
      url,
    });
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiRequestError({
      kind: "parse",
      status: response.status,
      code: "invalid_json",
      message: "Response was not valid JSON",
      url,
    });
  }
}

/* ------------------------------------------------------------------ *
 * Platform API payload types
 * ------------------------------------------------------------------ */

export interface ClusterInfo {
  name: string;
  version: string;
  provider: string;
  status: string;
  created_at?: string | null;
}

export interface OverviewCluster {
  id: string;
  name: string;
  cluster: ClusterInfo;
  nodes: { total: number; ready: number; cpu_capacity_cores: number; memory_capacity_gib: number };
  pods: { total: number; running: number; pending: number; failed: number; succeeded: number };
  deployments: { total: number; available: number; unavailable: number };
  namespaces: number;
  pods_by_namespace: Record<string, number>;
  resource_usage: {
    cpu_millicores: number;
    memory_mib: number;
    cpu_percent: number;
    memory_percent: number;
  };
  alerts: { firing: number; critical: number };
  gitops: { applications: number; synced: number; out_of_sync: number; degraded: number };
  throughput_rps: number;
  error_rate_percent: number;
}

export interface PlatformHealth {
  status: "ok" | "degraded" | (string & {});
  service: string;
  version: string;
  uptime_seconds: number;
  auth_enabled: boolean;
  cluster: { connected: boolean; name: string; error: string | null; data_source: DataSource };
  timestamp: string;
}

export interface NamespaceRow {
  name: string;
  status: string;
  pods: number;
  labels: Record<string, string>;
  age: string;
}

export interface WorkloadRow {
  kind: string;
  name: string;
  namespace: string;
  desired: number;
  ready: number;
  images: string[];
  age: string;
  status: string;
}

export interface PodContainer {
  name: string;
  ready: boolean;
  restarts: number;
  image: string;
}

export interface PodRow {
  name: string;
  namespace: string;
  phase: string;
  ready: string;
  restarts: number;
  node: string;
  age: string;
  ip: string;
  containers: PodContainer[];
  owner: string;
  labels: Record<string, string>;
}

export interface DeploymentCondition {
  type: string;
  status: string;
}

export interface DeploymentRow {
  name: string;
  namespace: string;
  desired: number;
  ready: number;
  updated: number;
  available: number;
  images: string[];
  strategy: string;
  age: string;
  conditions: DeploymentCondition[];
}

export interface ServicePort {
  port: number;
  target_port: number | string;
  protocol: string;
  name?: string;
}

export interface ServiceRow {
  name: string;
  namespace: string;
  type: string;
  cluster_ip: string;
  ports: ServicePort[];
  selector: Record<string, string>;
  age: string;
}

export interface MetricPoint {
  t: string;
  v: number;
}

export interface MetricSeries {
  name: string;
  unit: string;
  points: MetricPoint[];
}

export interface TopPod {
  pod: string;
  namespace: string;
  cpu_millicores: number;
  memory_mib: number;
}

export interface MetricsSummary {
  cpu_millicores: number;
  memory_mib: number;
  nodes: number;
  pods_measured: number;
  request_rate: number;
  error_rate_percent: number;
  p95_latency_ms: number;
}

export interface MetricsPayload {
  series: MetricSeries[];
  top_pods: TopPod[];
  summary: MetricsSummary;
}

export interface AlertRow {
  id: string;
  name: string;
  severity: string;
  status: string;
  service: string;
  namespace: string;
  summary: string;
  description: string;
  starts_at: string;
  fingerprint: string;
  runbook: string;
}

export interface GitOpsApplication {
  name: string;
  namespace: string;
  project: string;
  sync_status: string;
  health_status: string;
  revision: string;
  target_revision: string;
  path: string;
  destination: string;
  destination_namespace: string;
  auto_sync: boolean;
  last_synced_at: string | null;
  message: string;
}

export interface SecuritySummary {
  critical: number;
  high: number;
  medium: number;
  low: number;
  total: number;
}

export interface SecurityFinding {
  id: string;
  scanner: string;
  severity: string;
  resource: string;
  title: string;
  remediation: string;
}

export interface SecurityData {
  summary: SecuritySummary;
  scanners: string[];
  generated_at: string | null;
  findings: SecurityFinding[];
  note: string;
}

export interface LogEntry {
  timestamp: string;
  service: string;
  level: string;
  message: string;
  labels: Record<string, string>;
  fields: Record<string, unknown>;
}

/* ------------------------------------------------------------------ *
 * API Gateway / storefront payload types
 * ------------------------------------------------------------------ */

export interface GatewayDependency {
  status: "ok" | "degraded" | "down" | (string & {});
  http_status?: number;
  latency_ms: number;
  error?: string;
}

export interface GatewayHealth {
  status: string;
  service: string;
  version: string;
  dependencies: Record<string, GatewayDependency>;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  description: string;
  price_cents: number;
  currency: string;
  stock: number;
  active: boolean;
  updated_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  tier: "standard" | "premium" | "internal";
  created_at: string;
}

export interface OrderItem {
  product_id: string;
  sku: string;
  name: string;
  quantity: number;
  unit_price_cents: number;
}

export interface Order {
  id: string;
  user_id: string;
  status: string;
  total_cents: number;
  currency: string;
  created_at: string;
  items: OrderItem[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface CatalogOverview {
  products: Product[];
  product_total: number;
  recent_orders: Order[];
}

export interface CreateUserPayload {
  email: string;
  full_name: string;
  tier: User["tier"];
}

export interface CreateOrderPayload {
  user_id: string;
  items: Array<{ product_id: string; quantity: number }>;
  currency: string;
}

/* ------------------------------------------------------------------ *
 * Typed endpoint wrappers
 * ------------------------------------------------------------------ */

export interface PageQuery {
  limit?: number;
  offset?: number;
}

export const api = {
  /* platform-api ------------------------------------------------- */
  health: () => request<PlatformHealth>("/api/health"),

  clusterOverview: async (): Promise<Envelope<OverviewCluster>> => {
    const payload = await request<Envelope<OverviewCluster[]>>("/api/clusters");
    const first = payload.data[0];
    if (!first) {
      throw new ApiRequestError({
        kind: "parse",
        status: 200,
        code: "empty_cluster_list",
        message: "Platform API returned no clusters",
        url: buildUrl("platform", "/api/clusters"),
      });
    }
    return { data: first, meta: payload.meta };
  },

  namespaces: (params: PageQuery & { q?: string }) =>
    request<Envelope<NamespaceRow[]>>("/api/namespaces", { query: { ...params } }),

  workloads: (params: PageQuery & { namespace?: string; kind?: string }) =>
    request<Envelope<WorkloadRow[]>>("/api/workloads", { query: { ...params } }),

  pods: (params: PageQuery & { namespace?: string; phase?: string }) =>
    request<Envelope<PodRow[]>>("/api/pods", { query: { ...params } }),

  deployments: (params: PageQuery & { namespace?: string }) =>
    request<Envelope<DeploymentRow[]>>("/api/deployments", { query: { ...params } }),

  services: (params: PageQuery & { namespace?: string }) =>
    request<Envelope<ServiceRow[]>>("/api/services", { query: { ...params } }),

  metrics: () => request<Envelope<MetricsPayload>>("/api/metrics"),

  alerts: (params: { severity?: string; status?: string }) =>
    request<Envelope<AlertRow[]>>("/api/alerts", { query: { ...params } }),

  gitops: () => request<Envelope<GitOpsApplication[]>>("/api/gitops/status"),

  security: (params: PageQuery & { severity?: string }) =>
    request<Envelope<SecurityData>>("/api/security/findings", { query: { ...params } }),

  logs: (params: { namespace?: string; pod?: string; level?: string; limit?: number }) =>
    request<Envelope<LogEntry[]>>("/api/logs", { query: { ...params } }),

  /* api-gateway (storefront) -------------------------------------- */
  gatewayHealth: () => request<GatewayHealth>("/api/health", { base: "gateway" }),

  catalogOverview: () => request<CatalogOverview>("/api/catalog/overview", { base: "gateway" }),

  listOrders: (limit = 20) =>
    request<Paginated<Order>>("/api/orders", { base: "gateway", query: { limit } }),

  createUser: (payload: CreateUserPayload) =>
    request<User>("/api/users", { base: "gateway", method: "POST", body: payload }),

  createOrder: (payload: CreateOrderPayload, idempotencyKey: string) =>
    request<Order>("/api/orders", {
      base: "gateway",
      method: "POST",
      body: payload,
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};
