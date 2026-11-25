import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PersonaImpressions, PersonaTakeaway } from "./PersonaImpressions";

describe("PersonaImpressions", () => {
  it("counts friction from the displayed impressions when stored totals differ", () => {
    const payload = {
      total_impressions: 18, friction_count: 18,
      personas: [{ persona_name: "Keyboard user", friction_count: 18,
        impressions: [{ kind: "focus_indicator_invisible", journey_url: "https://shop.example.test/" }],
        keyboard_walk: { tabs: 2, steps: [{ name: "Start", indicator_visible: true }, { name: "Next", indicator_visible: false }] },
      }],
    };
    render(<><PersonaTakeaway payload={payload} /><PersonaImpressions payload={payload} /></>);
    expect(screen.getByText("1 recorded impression from 1 persona · 1 about friction")).toBeVisible();
    expect(screen.getByText("1 friction note")).toBeVisible();
    expect(screen.getByText(/Mentioned by 1 of 1 personas/)).toBeVisible();
    expect(screen.getByText("Keyboard record")).toBeVisible();
  });

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
    expect(screen.getByRole("heading", { name: "Persona impressions" })).toBeTruthy();
    expect(screen.getByText(/I waited 4\.2 seconds/)).toBeTruthy();
    expect(screen.getByText(/loaded in 4\.2s/i)).toBeTruthy();
    expect(screen.getByText("Impatient mobile user")).toBeTruthy();
    expect(screen.queryByText(/Not ready yet|Ready to ship/)).toBeNull();
  });
});
