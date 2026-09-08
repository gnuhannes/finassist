import { expect, test } from "@playwright/test";

/**
 * Smoke journey: seed an account through the API, then confirm the app shell
 * renders, the frontend reaches the backend through the Vite proxy, and
 * client-side navigation works. This is the seed of the E2E layer — grow it
 * toward the real import -> visualize -> insights flow.
 */
test("app shell loads, talks to the API, and navigates", async ({ page, request }) => {
  const seeded = await request.post("/api/accounts", {
    data: { name: "E2E Checking", currency: "EUR" },
  });
  expect(seeded.ok()).toBeTruthy();

  await page.goto("/");

  // Shell + dashboard rendered from live API data.
  await expect(page.getByRole("navigation")).toContainText("My Finances");
  await expect(page.getByRole("heading", { name: "My Private Finances" })).toBeVisible();
  await expect(page.getByText("Local-first dashboard.")).toBeVisible();
  await expect(page.getByText(/Failed to load report/i)).toHaveCount(0);

  // Client-side routing to the Import page.
  await page.getByRole("link", { name: "Import" }).click();
  await expect(page).toHaveURL(/\/import$/);
  await expect(page.getByRole("button", { name: "Import CSV" })).toBeVisible();
});
