import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function checkPage(page: Page) {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/me", (route) => route.fulfill({ status: 401, json: { detail: "Unauthenticated" } }));
});

test("landing explains the product and connects to How and real sign-in", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Know if your app is ready");
  await expect(page.getByRole("textbox", { name: "YOUR APP'S ADDRESS" }).first()).toBeVisible();
  const exampleTab = page.getByRole("tab", { name: "Show me an example" });
  await exampleTab.click();
  await expect(exampleTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText(/See our Thread & Co. test below/)).toBeVisible();
  await checkPage(page);
  await page.screenshot({ path: testInfo.outputPath("landing.png"), fullPage: true });
  await page.locator("footer").getByRole("button", { name: "How it works", exact: true }).click();
  await expect(page).toHaveURL(/\/how-it-works$/);
  await expect(page.getByRole("heading", { name: "Know what each category proves." })).toBeVisible();
  await page.getByRole("navigation", { name: "Product navigation", exact: true }).getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in to MarketTwin" })).toBeVisible();
  await page.getByRole("link", { name: "MarketTwin home" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("How explains evidence limits and remains accessible without the API", async ({ page }, testInfo) => {
  await page.goto("/how-it-works");
  await expect(page.getByText(/Repetition across simulated testers does not confirm a defect/)).toBeVisible();
  await page.getByText("Missing or uncaptured artifact", { exact: true }).click();
  await expect(page.getByText(/Adjacent screenshots are never substituted/)).toBeVisible();
  await checkPage(page);
  await page.screenshot({ path: testInfo.outputPath("how.png"), fullPage: true });
});

test("keyboard navigation, URL validation and reduced motion remain usable", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const start = page.locator("header").getByRole("button", { name: "START A TEST", exact: true });
  await start.focus();
  await page.keyboard.press("Enter");
  const address = page.getByRole("textbox", { name: "YOUR APP'S ADDRESS" }).first();
  await expect(address).toBeFocused();
  await address.fill("not a valid address");
  await page.keyboard.press("Enter");
  await expect(address).toHaveAttribute("aria-invalid", "true");
  const example = page.getByRole("tab", { name: "Show me an example" });
  await example.focus();
  await page.keyboard.press("Enter");
  await expect(example).toHaveAttribute("aria-selected", "true");
  await page.goto("/how-it-works");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#public-content")).toBeFocused();
});

test("login form exposes service failure and permits retry", async ({ page }, testInfo) => {
  await page.route("**/api/v1/auth/local/login", (route) => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.goto("/login");
  await page.getByRole("textbox", { name: /email/i }).fill("reviewer@example.test");
  await page.getByRole("button", { name: "Continue to workspace", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("The login service is unavailable");
  await expect(page.getByRole("alert")).toBeFocused();
  await expect(page.getByRole("button", { name: "Continue to workspace", exact: true })).toBeEnabled();
  await checkPage(page);
  await page.screenshot({ path: testInfo.outputPath("login-error.png"), fullPage: true });
});

test("callback stays honest about unavailable production authentication", async ({ page }, testInfo) => {
  await page.goto("/auth/callback");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Production sign-in is not available here");
  await expect(page.getByRole("link", { name: "Return to sign in" })).toHaveAttribute("href", "/login");
  await checkPage(page);
  await page.screenshot({ path: testInfo.outputPath("callback.png"), fullPage: true });
});

test("public pages fit the required viewport widths", async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [name, path] of [["landing", "/"], ["how", "/how-it-works"], ["login", "/login"], ["callback", "/auth/callback"]]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect(await page.evaluate(() => ({ width: innerWidth, content: document.documentElement.scrollWidth })), `${name} at ${width}px`).toMatchObject({ width });
      expect(await page.evaluate(() => document.documentElement.scrollWidth), `${name} overflows ${width}px`).toBeLessThanOrEqual(width + 1);
      await page.screenshot({ path: testInfo.outputPath(`${name}-${width}.png`), fullPage: true });
    }
  }
});
