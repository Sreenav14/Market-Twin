import { ReactNode, useEffect } from "react";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · MarketTwin`;
  }, [title]);

  return (
    <header className="page-header">
      <div className="page-header-copy">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action ? <div className="page-action">{action}</div> : null}
    </header>
  );
}
