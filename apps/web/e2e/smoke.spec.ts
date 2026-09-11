import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("logged-out entry point is usable and accessible", async ({ page }, testInfo) => {
  await page.route("**/api/v1/me", route => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Sign in required." }) }));
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: /Build an app/ })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious")).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await mkdir("../../docs/ui-review", { recursive: true });
  await page.screenshot({ path: `../../docs/ui-review/signin-${testInfo.project.name}.png`, fullPage: true });
});
