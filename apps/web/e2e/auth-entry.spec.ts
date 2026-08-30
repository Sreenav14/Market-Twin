import { expect, test } from "@playwright/test";

test("sign in links to account creation", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("link", { name: "Create an account" }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole("heading", { name: "Create an account" })).toBeVisible();
});

test("local signup is truthful and returns to sign in", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Work email").fill("new.user@example.com");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Account creation is not enabled in local development.")).toBeVisible();
  await page.getByRole("link", { name: "Sign in instead" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
