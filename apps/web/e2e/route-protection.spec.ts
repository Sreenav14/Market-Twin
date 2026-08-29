import { expect, test } from "@playwright/test";

test("protected routes return an unauthenticated user to sign in", async ({ page }) => {
  await page.goto("/applications");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Test the experience before customers do." })).toBeVisible();
});
