import { expect, test } from "@playwright/test";

test("protected routes return an unauthenticated user to sign in", async ({ page }) => {
  await page.route("**/api/v1/me", route => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Sign in required." }) }));
  await page.goto("/applications");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: /Build an app/ })).toBeVisible();
});
