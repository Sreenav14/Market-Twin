import { ReactNode } from "react";

import { BrandMark } from "../../components/ui/BrandMark";

export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="access-shell">
      <header className="access-header">
        <div className="access-brand">
          <BrandMark />
          <div>
            <strong>MarketTwin</strong>
            <span>Product preflight</span>
          </div>
        </div>
        <span className="access-environment">Local development</span>
      </header>

      <main className="access-main">
        <section className="access-product" aria-labelledby="access-product-title">
          <p className="access-kicker">Before release</p>
          <h1 id="access-product-title">See where product experiences diverge.</h1>
          <p className="access-product-copy">
            Authorize a target, describe the outcome you care about, and review evidence from independent user journeys in one workspace.
          </p>

          <ol className="access-sequence" aria-label="MarketTwin study workflow">
            <li><span>01</span><div><strong>Authorize a target</strong><p>Keep the testing boundary explicit.</p></div></li>
            <li><span>02</span><div><strong>Describe the product goal</strong><p>MarketTwin plans relevant perspectives dynamically.</p></div></li>
            <li><span>03</span><div><strong>Review the evidence</strong><p>Trace findings back to the journeys that produced them.</p></div></li>
          </ol>
        </section>

        <section className="access-panel">
          {children}
        </section>
      </main>

      <footer className="access-footer">
        <span>Authorized targets</span>
        <span>Independent journeys</span>
        <span>Evidence-backed findings</span>
      </footer>
    </div>
  );
}
