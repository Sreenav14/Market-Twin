import { useEffect } from "react";

export function FutureStagePage({ title, stage, description }: { title: string; stage: string; description: string }) {
  useEffect(() => {
    document.title = `${title} · MarketTwin`;
  }, [title]);

  return (
    <section className="panel future-stage">
      <span className="future-kicker">{stage} · Backend milestone required</span>
      <h2>{title}</h2>
      <p>{description}</p>
      <p>This page is intentionally not simulated. It will display product data only after the corresponding planning, execution, evidence, evaluation, or administration API is implemented.</p>
    </section>
  );
}
