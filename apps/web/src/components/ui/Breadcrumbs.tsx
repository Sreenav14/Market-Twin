import { Link } from "react-router-dom";

/**
 * The one breadcrumb trail (Phase 2b, Spec 1 §6 family). Use ONLY where
 * a page has a real parent path — never invent hierarchy. The last item
 * is the current page: plain text with aria-current, never a link.
 */
export function Breadcrumbs({
  items,
}: {
  items: { label: string; to?: string }[];
}) {
  return (
    <nav aria-label="Breadcrumb" className="breadcrumbs">
      <ol>
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${item.label}-${i}`}>
              {i > 0 ? (
                <span className="breadcrumb-sep" aria-hidden="true">
                  ›
                </span>
              ) : null}
              {last || !item.to ? (
                <span aria-current={last ? "page" : undefined}>{item.label}</span>
              ) : (
                <Link to={item.to}>{item.label}</Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
