import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/me", (route) => route.fulfill({ status: 401, json: { detail: "Unauthenticated" } }));
});

test("public home explains the product and connects to How and login", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("through a user's");
  await expect(page.getByText("Interactive example", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Choose a plan/ }).click();
  await expect(page.getByRole("button", { name: /Choose a plan/ })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".mt-demo-evidence h3")).toHaveText("Choose a plan");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("home.png"), fullPage: true });
  await page.getByRole("link", { name: "See how it works" }).click();
  await expect(page).toHaveURL(/\/how-it-works$/);
  await expect(page.getByRole("heading", { name: "Know what each finding means." })).toBeVisible();
  await page.getByRole("navigation", { name: "Product", exact: true }).getByRole("link", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in to MarketTwin" })).toBeVisible();
  await page.getByRole("link", { name: "MarketTwin home" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("How describes verification boundaries and stays accessible without the API", async ({ page }, testInfo) => {
  await page.route("**/api/**", (route) => route.abort());
  await page.goto("/how-it-works");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText(/Repetition does not confirm a bug/)).toBeVisible();
  await page.getByText("Why are several similar observations still unverified?", { exact: true }).click();
  await expect(page.getByText(/Simulated personas can share assumptions/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("how.png"), fullPage: true });
});

test("keyboard controls and reduced motion work on the home page", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#public-content")).toBeFocused();
  const button = page.getByRole("button", { name: /Review the next step/ });
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(button).toHaveAttribute("aria-pressed", "true");
  expect(await page.locator(".mt-hero-copy").evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
});

test("login form remains usable when the session service fails", async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in to MarketTwin" })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill("reviewer@example.test");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("The login service is unavailable");
  await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeEnabled();
});
