import { ReactNode, useEffect } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
  crumbs,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  /** A Breadcrumbs trail for pages with a real parent path (Phase 2b). */
  crumbs?: ReactNode;
}) {
  useEffect(() => {
    document.title = `${title} · MarketTwin`;
  }, [title]);

  return (
    <header className="page-header">
      {crumbs}
      <div className="page-header-copy">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action ? <div className="page-action">{action}</div> : null}
    </header>
  );
}
