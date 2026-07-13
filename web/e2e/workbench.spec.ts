import { expect, test } from "@playwright/test";

test("browse, launch, independently pause, inspect, cancel, and reopen evidence", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Run library" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Strict-FIFO diverge inspection fixture/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Bounded Sioux Falls · 100 packets/ })).toBeVisible();
  await expect(page.getByText("Link inspection")).toBeVisible();
  await page.getByRole("button", { name: "P1", exact: true }).click();
  await expect(page.getByText("Packet inspection")).toBeVisible();
  await page.getByRole("button", { name: "Close packet inspection" }).click();

  await page.getByRole("button", { name: /Bounded Sioux Falls · 100 packets/ }).click();
  await expect(page.getByRole("heading", { name: "Cumulative boundary counts" })).toBeVisible();
  await page.getByLabel("Replay tick").fill("5");
  await expect(page.getByText("Movement allocation")).toBeVisible();
  await expect(page.getByText("Python allocation evidence · t5")).toBeVisible();
  await expect(page.locator(".movement-meta")).toContainText("N003");

  await page.getByRole("button", { name: "New sanctioned run" }).click();
  await expect(page.getByRole("dialog", { name: "New sanctioned run" })).toBeVisible();
  const packetCount = page.getByLabel("Packet count · unit packets");
  await packetCount.fill("200");
  await page.getByLabel("Optional run label").fill("E2E retained partial");
  await page.getByRole("button", { name: "Launch Python run" }).click();
  await expect(page.getByText(/Python run · (running|setting_up|resolving)/)).toBeVisible();

  // Viewer transport is presentation state only; engine control remains separate.
  await page.getByRole("button", { name: "Pause viewer" }).click();
  await expect(page.getByRole("button", { name: "Resume viewer at live head" })).toBeVisible();
  const progressBefore = await page.locator(".live-progress").textContent();
  await page.waitForTimeout(120);
  await expect.poll(() => page.locator(".live-progress").textContent()).not.toBe(progressBefore);
  await expect(page.getByRole("button", { name: "Pause run" })).toBeVisible();

  await page.getByRole("button", { name: "Pause run" }).click();
  await expect(page.getByRole("button", { name: "Resume run" })).toBeVisible();
  await page.getByRole("button", { name: "Resume run" }).click();
  await expect(page.getByRole("button", { name: "Cancel & retain" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel & retain" }).click();
  await expect(page.getByText("Python run · cancelled")).toBeVisible();

  await page.getByRole("button", { name: "Refresh artifact library" }).click();
  await expect(page.getByRole("button", { name: /E2E retained partial/ })).toBeVisible();
  await page.getByRole("button", { name: /E2E retained partial/ }).click();
  await expect(page.getByRole("heading", { name: "E2E retained partial" })).toBeVisible();
});
