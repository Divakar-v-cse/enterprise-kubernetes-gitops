import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, normaliseError } from "../lib/api";
import type {
  CatalogOverview,
  GatewayHealth,
  NormalisedError,
  Order,
  Product,
  User,
} from "../lib/api";
import { useAsync } from "../lib/useApi";
import { Badge } from "../components/Badge";
import { EmptyState } from "../components/EmptyState";
import { Loading } from "../components/Loading";
import { formatCents, formatDateTime, relativeTime, statusTone, text } from "../lib/format";
import { useSettings } from "../lib/settings";

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function ErrorLine({ error, onRetry }: { error: NormalisedError; onRetry?: () => void }) {
  return (
    <div className="state state--error state--compact" role="alert">
      <strong>{error.message}</strong>
      <p className="mono-sm muted">
        {error.kind}
        {error.status ? ` · HTTP ${error.status}` : ""} · {error.code}
      </p>
      {onRetry ? (
        <button type="button" className="button button--ghost button--sm" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

function ProductCard({ product }: { product: Product }) {
  const soldOut = product.stock <= 0;
  return (
    <article className="product-card">
      <div className="product-card__head">
        <span className="product-card__sku">{product.sku}</span>
        <Badge tone={product.active ? "ok" : "warn"}>{product.active ? "active" : "inactive"}</Badge>
      </div>
      <h3 className="product-card__name">{product.name}</h3>
      <p className="product-card__desc">{product.description || "No description provided."}</p>
      <div className="product-card__foot">
        <strong className="product-card__price">{formatCents(product.price_cents, product.currency)}</strong>
        <span className={soldOut ? "value--error" : "muted"}>
          {soldOut ? "out of stock" : `${product.stock} in stock`}
        </span>
      </div>
    </article>
  );
}

export function Storefront() {
  const { config } = useSettings();
  const catalog = useAsync<CatalogOverview>(() => api.catalogOverview());
  const gateway = useAsync<GatewayHealth>(() => api.gatewayHealth());

  const [orders, setOrders] = useState<Order[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [ordersError, setOrdersError] = useState<NormalisedError | null>(null);

  const [userForm, setUserForm] = useState({ email: "", full_name: "", tier: "standard" as User["tier"] });
  const [userResult, setUserResult] = useState<User | null>(null);
  const [userError, setUserError] = useState<NormalisedError | null>(null);
  const [userBusy, setUserBusy] = useState(false);

  const [orderForm, setOrderForm] = useState({ user_id: "", product_id: "", quantity: 1, currency: "USD" });
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => newIdempotencyKey());
  const [orderResult, setOrderResult] = useState<Order | null>(null);
  const [orderError, setOrderError] = useState<NormalisedError | null>(null);
  const [orderBusy, setOrderBusy] = useState(false);

  const loadOrders = async () => {
    setOrdersLoading(true);
    setOrdersError(null);
    try {
      const payload = await api.listOrders(20);
      setOrders(payload.items);
    } catch (error) {
      setOrdersError(normaliseError(error));
    } finally {
      setOrdersLoading(false);
    }
  };

  useEffect(() => {
    void loadOrders();
  }, []);

  const products = catalog.data?.products ?? [];

  useEffect(() => {
    if (!orderForm.product_id && products.length > 0) {
      setOrderForm((current) => ({ ...current, product_id: products[0].id, currency: products[0].currency }));
    }
  }, [products, orderForm.product_id]);

  const submitUser = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setUserBusy(true);
    setUserError(null);
    setUserResult(null);
    try {
      const user = await api.createUser({
        email: userForm.email.trim(),
        full_name: userForm.full_name.trim(),
        tier: userForm.tier,
      });
      setUserResult(user);
      setOrderForm((current) => ({ ...current, user_id: user.id }));
    } catch (error) {
      setUserError(normaliseError(error));
    } finally {
      setUserBusy(false);
    }
  };

  const submitOrder = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setOrderBusy(true);
    setOrderError(null);
    setOrderResult(null);
    try {
      const created = await api.createOrder(
        {
          user_id: orderForm.user_id.trim(),
          items: [{ product_id: orderForm.product_id, quantity: Number(orderForm.quantity) }],
          currency: orderForm.currency,
        },
        idempotencyKey,
      );
      setOrderResult(created);
      setIdempotencyKey(newIdempotencyKey());
      await loadOrders();
    } catch (error) {
      setOrderError(normaliseError(error));
    } finally {
      setOrderBusy(false);
    }
  };

  const selectedProduct = products.find((product) => product.id === orderForm.product_id);

  return (
    <div className="store-shell">
      <header className="store-header">
        <div className="store-header__brand">
          <span className="sidebar__logo" aria-hidden="true">◈</span>
          <div>
            <h1 className="store-header__title">Storefront demo</h1>
            <p className="store-header__sub">
              api-gateway → user-service · product-service · order-service
            </p>
          </div>
        </div>
        <div className="store-header__actions">
          <span className="topbar__endpoint" title={config.gatewayBase}>
            <span className="topbar__endpoint-label">Gateway</span>
            <code>{config.gatewayBase.replace(/^https?:\/\//, "")}</code>
          </span>
          <Link className="button button--ghost button--sm" to="/ops">
            ← Ops dashboard
          </Link>
        </div>
      </header>

      <div className="store-note" role="note">
        <strong>Storefront demo.</strong> This area exercises the microservices contract
        (API-key-protected writes, idempotent order creation). It is separate from the read-only
        ops dashboard, which talks to the platform API instead.
      </div>

      <main className="store-main">
        <section className="card" aria-labelledby="gateway-health">
          <header className="card__head">
            <h2 id="gateway-health" className="card__title">Gateway health</h2>
            <button type="button" className="button button--ghost button--sm" onClick={gateway.reload}>
              Re-probe
            </button>
          </header>
          {gateway.loading ? <Loading label="Probing gateway health" rows={2} /> : null}
          {gateway.error ? <ErrorLine error={gateway.error} onRetry={gateway.reload} /> : null}
          {gateway.data ? (
            <>
              <div className="badge-row">
                <Badge tone={statusTone(gateway.data.status)}>{gateway.data.status}</Badge>
                <span className="muted">
                  {gateway.data.service} · v{gateway.data.version}
                </span>
              </div>
              <div className="dep-grid">
                {Object.entries(gateway.data.dependencies).map(([name, dependency]) => (
                  <div className="dep" key={name}>
                    <div className="dep__name">
                      <Badge tone={statusTone(dependency.status)}>{dependency.status}</Badge>
                      <code>{name}</code>
                    </div>
                    <div className="dep__meta">
                      {dependency.latency_ms} ms
                      {dependency.http_status ? ` · HTTP ${dependency.http_status}` : ""}
                    </div>
                    {dependency.error ? <div className="dep__error mono-sm">{dependency.error}</div> : null}
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </section>

        <section className="card" aria-labelledby="catalog">
          <header className="card__head">
            <h2 id="catalog" className="card__title">Product catalog</h2>
            <span className="card__hint">
              {catalog.data ? `${catalog.data.product_total} products · ${catalog.data.recent_orders.length} recent orders` : "GET /api/catalog/overview"}
            </span>
          </header>
          {catalog.loading ? <Loading label="Loading catalog" rows={3} /> : null}
          {catalog.error ? <ErrorLine error={catalog.error} onRetry={catalog.reload} /> : null}
          {!catalog.loading && !catalog.error && products.length === 0 ? (
            <EmptyState
              title="Catalog is empty"
              message="The product service returned no products. Seed data via the product service before ordering."
            />
          ) : null}
          {products.length > 0 ? (
            <div className="product-grid">
              {products.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          ) : null}
        </section>

        <div className="grid grid--two">
          <section className="card" aria-labelledby="create-user">
            <header className="card__head">
              <h2 id="create-user" className="card__title">Create user</h2>
              <span className="card__hint">POST /api/users · X-API-Key</span>
            </header>
            <form className="form" onSubmit={submitUser}>
              <div className="field">
                <label htmlFor="user-email">Email</label>
                <input
                  id="user-email"
                  className="input"
                  type="email"
                  required
                  value={userForm.email}
                  placeholder="ada@example.com"
                  onChange={(event) => setUserForm({ ...userForm, email: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="user-name">Full name</label>
                <input
                  id="user-name"
                  className="input"
                  type="text"
                  required
                  minLength={2}
                  maxLength={120}
                  value={userForm.full_name}
                  placeholder="Ada Lovelace"
                  onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="user-tier">Tier</label>
                <select
                  id="user-tier"
                  className="input"
                  value={userForm.tier}
                  onChange={(event) => setUserForm({ ...userForm, tier: event.target.value as User["tier"] })}
                >
                  <option value="standard">standard</option>
                  <option value="premium">premium</option>
                  <option value="internal">internal</option>
                </select>
              </div>
              <div className="form__actions">
                <button type="submit" className="button" disabled={userBusy}>
                  {userBusy ? "Creating…" : "Create user"}
                </button>
              </div>
            </form>
            {userError ? <ErrorLine error={userError} /> : null}
            {userResult ? (
              <div className="state state--ok state--compact" role="status">
                <strong>User created</strong>
                <dl className="facts">
                  <div><dt>ID</dt><dd><code>{userResult.id}</code></dd></div>
                  <div><dt>Email</dt><dd>{userResult.email}</dd></div>
                  <div><dt>Name</dt><dd>{userResult.full_name}</dd></div>
                  <div><dt>Tier</dt><dd>{userResult.tier}</dd></div>
                  <div><dt>Created</dt><dd>{formatDateTime(userResult.created_at)}</dd></div>
                </dl>
              </div>
            ) : null}
          </section>

          <section className="card" aria-labelledby="create-order">
            <header className="card__head">
              <h2 id="create-order" className="card__title">Create order</h2>
              <span className="card__hint">POST /api/orders · idempotent</span>
            </header>
            <form className="form" onSubmit={submitOrder}>
              <div className="field">
                <label htmlFor="order-user">User ID</label>
                <input
                  id="order-user"
                  className="input"
                  type="text"
                  required
                  value={orderForm.user_id}
                  placeholder="Create a user above, or paste an ID"
                  onChange={(event) => setOrderForm({ ...orderForm, user_id: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="order-product">Product</label>
                <select
                  id="order-product"
                  className="input"
                  required
                  value={orderForm.product_id}
                  onChange={(event) => setOrderForm({ ...orderForm, product_id: event.target.value })}
                >
                  <option value="" disabled>
                    {products.length === 0 ? "No products available" : "Select a product"}
                  </option>
                  {products.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.name} — {formatCents(product.price_cents, product.currency)} ({product.stock} in stock)
                    </option>
                  ))}
                </select>
              </div>
              <div className="field field--row">
                <div>
                  <label htmlFor="order-qty">Quantity</label>
                  <input
                    id="order-qty"
                    className="input"
                    type="number"
                    min={1}
                    max={50}
                    required
                    value={orderForm.quantity}
                    onChange={(event) => setOrderForm({ ...orderForm, quantity: Number(event.target.value) })}
                  />
                </div>
                <div>
                  <label htmlFor="order-currency">Currency</label>
                  <input
                    id="order-currency"
                    className="input"
                    type="text"
                    minLength={3}
                    maxLength={3}
                    required
                    value={orderForm.currency}
                    onChange={(event) => setOrderForm({ ...orderForm, currency: event.target.value.toUpperCase() })}
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor="idem-key">Idempotency-Key (generated client-side)</label>
                <div className="field__row">
                  <input id="idem-key" className="input mono-sm" type="text" readOnly value={idempotencyKey} />
                  <button
                    type="button"
                    className="button button--ghost button--sm"
                    onClick={() => setIdempotencyKey(newIdempotencyKey())}
                  >
                    Regenerate
                  </button>
                </div>
              </div>
              {selectedProduct ? (
                <p className="muted">
                  Line total: {formatCents(selectedProduct.price_cents * orderForm.quantity, orderForm.currency)}
                </p>
              ) : null}
              <div className="form__actions">
                <button type="submit" className="button" disabled={orderBusy || products.length === 0}>
                  {orderBusy ? "Submitting…" : "Submit order"}
                </button>
              </div>
            </form>
            {orderError ? <ErrorLine error={orderError} /> : null}
            {orderResult ? (
              <div className="state state--ok state--compact" role="status">
                <strong>Order accepted</strong>
                <dl className="facts">
                  <div><dt>Order</dt><dd><code>{orderResult.id}</code></dd></div>
                  <div><dt>Status</dt><dd><Badge tone={statusTone(orderResult.status)}>{orderResult.status}</Badge></dd></div>
                  <div><dt>Total</dt><dd>{formatCents(orderResult.total_cents, orderResult.currency)}</dd></div>
                  <div><dt>Items</dt><dd>{orderResult.items.length}</dd></div>
                </dl>
                <p className="muted mono-sm">
                  The idempotency key was rotated after this submission; retrying with the same key
                  returns the same order instead of creating a duplicate.
                </p>
              </div>
            ) : null}
          </section>
        </div>

        <section className="card" aria-labelledby="orders">
          <header className="card__head">
            <h2 id="orders" className="card__title">Orders</h2>
            <button type="button" className="button button--ghost button--sm" onClick={() => void loadOrders()}>
              Refresh orders
            </button>
          </header>
          {ordersLoading ? <Loading label="Loading orders" rows={3} /> : null}
          {ordersError ? <ErrorLine error={ordersError} onRetry={() => void loadOrders()} /> : null}
          {!ordersLoading && !ordersError && orders.length === 0 ? (
            <EmptyState title="No orders yet" message="Create a user and submit an order to populate this list." />
          ) : null}
          {orders.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Orders returned by the order service</caption>
                <thead>
                  <tr>
                    <th scope="col">Order</th>
                    <th scope="col">User</th>
                    <th scope="col">Status</th>
                    <th scope="col">Items</th>
                    <th scope="col" style={{ textAlign: "right" }}>Total</th>
                    <th scope="col">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => (
                    <tr key={order.id}>
                      <td><code>{order.id}</code></td>
                      <td><code>{text(order.user_id)}</code></td>
                      <td><Badge tone={statusTone(order.status)}>{order.status}</Badge></td>
                      <td>
                        {order.items.map((item) => (
                          <div key={`${order.id}-${item.product_id}`} className="mono-sm">
                            {item.quantity}× {item.sku} ({item.name}) @ {formatCents(item.unit_price_cents, order.currency)}
                          </div>
                        ))}
                      </td>
                      <td style={{ textAlign: "right" }}>{formatCents(order.total_cents, order.currency)}</td>
                      <td title={formatDateTime(order.created_at)}>{relativeTime(order.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </main>

      <footer className="app-footer">
        <span>Writes require X-API-Key · orders require Idempotency-Key</span>
        <span>Demo catalog data comes from the product service</span>
      </footer>
    </div>
  );
}
