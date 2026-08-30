import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("logged-out entry point is usable and accessible", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "See where product experiences diverge." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Work email")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  await expect(page.getByRole("link", { name: "Create an account" })).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious")).toEqual([]);
});
