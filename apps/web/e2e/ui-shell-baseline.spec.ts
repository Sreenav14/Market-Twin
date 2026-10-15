import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

const syntheticUser = {
  id: "ui-review-user",
  email: "reviewer@example.test",
  normalized_email: "reviewer@example.test",
  display_name: "UI review",
};
const syntheticWorkspace = {
  id: "ui-review-workspace",
  name: "Review workspace",
  status: "active",
  role: "owner",
};

async function installSyntheticWorkspace(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/me") return route.fulfill({ json: syntheticUser });
    if (path === "/api/v1/workspaces") return route.fulfill({ json: [syntheticWorkspace] });
    if (path === "/api/v1/workspaces/ui-review-workspace/applications") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: "Synthetic UI fixture has no matching route." } });
  });
}

const screenshotDirectory = path.resolve(process.cwd(), "../../.local/ui-redesign/screenshots");
await mkdir(screenshotDirectory, { recursive: true });

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
  { name: "small-mobile", width: 320, height: 700 },
  { name: "zoom-200-reflow", width: 640, height: 900 },
]) {
  test(`synthetic workspace shell fits ${viewport.name} and passes WCAG 2.1 AA axe checks`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await installSyntheticWorkspace(page);
    await page.goto("/overview");
    await expect(page.getByRole("heading", { name: "Workspace overview" })).toBeVisible();
    const screenshot = path.join(screenshotDirectory, `workspace-${viewport.name}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width + 1);
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(audit.violations).toEqual([]);

    if (viewport.width <= 980) {
      const trigger = page.getByRole("button", { name: "Open navigation" });
      await expect(trigger).toBeVisible();
      await trigger.click();
      const dialog = page.getByRole("dialog", { name: "Workspace navigation" });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
      await page.screenshot({ path: path.join(screenshotDirectory, `workspace-${viewport.name}-navigation.png`), fullPage: true });
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(trigger).toBeFocused();

      await trigger.click();
      const openedDrawer = page.getByRole("dialog", { name: "Workspace navigation" });
      await openedDrawer.getByRole("link", { name: "Applications" }).click();
      await expect(page).toHaveURL(/\/applications$/);
      await expect(page.locator("#main-content")).toBeFocused();
      await expect(openedDrawer).toBeHidden();
    }
  });
}
