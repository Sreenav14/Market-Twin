import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PersonaImpressions } from "./PersonaImpressions";

describe("PersonaImpressions", () => {
  it("renders anchored quotes per persona and never a verdict", () => {
    render(
      <PersonaImpressions
        payload={{
          run_kind: "persona",
          total_impressions: 2,
          friction_count: 1,
          personas: [
            {
              persona_id: "impatient_mobile-1",
              persona_name: "Impatient mobile user",
              persona_type: "impatient_mobile",
              friction_count: 1,
              impressions: [
                {
                  kind: "slow_load",
                  quote: "I waited 4.2 seconds for Home to load.",
                  journey_url: "https://shop.example.test/",
                  page_title: "Home",
                  signal: { load_ms: 4200 },
                },
                {
                  kind: "fast_and_clean",
                  quote: "Checkout loaded fast and nothing broke. That felt easy.",
                  journey_url: "https://shop.example.test/checkout",
                  page_title: "Checkout",
                  signal: { load_ms: 300 },
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("What it felt like")).toBeTruthy();
    expect(screen.getByText(/I waited 4\.2 seconds/)).toBeTruthy();
    expect(screen.getByText(/loaded in 4\.2s/)).toBeTruthy();
    expect(screen.getByText("Impatient mobile user")).toBeTruthy();
    expect(screen.queryByText(/Not ready yet|Ready to ship/)).toBeNull();
  });
});
