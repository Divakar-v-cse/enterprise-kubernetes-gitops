import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <main className="notfound">
      <p className="notfound__code">404</p>
      <h1 className="notfound__title">Page not found</h1>
      <p className="notfound__text">
        This route is not part of the platform dashboard. The ops dashboard exposes 14 pages
        under <code>/ops</code>; the microservices storefront lives at <code>/store</code>.
      </p>
      <div className="notfound__actions">
        <Link className="button" to="/ops">Back to platform overview</Link>
        <Link className="button button--ghost" to="/store">Open storefront demo</Link>
      </div>
    </main>
  );
}
