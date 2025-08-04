import { test, expect } from '@playwright/test';

test.describe('API Fallback in Browser', () => {
  test('should show fallback notice when using sample data', async ({ page }) => {
    // Test with a race ID that should trigger fallback
    await page.goto('/races/test-fallback-race');
    
    // Wait for the page to load
    await page.waitForSelector('h1');
    
    // Should show the fallback notice
    await expect(page.locator('.fallback-notice')).toBeVisible();
    await expect(page.locator('.fallback-title')).toContainText('Using Sample Data');
    
    // Should still show candidate data
    await expect(page.locator('.candidate-grid')).toBeVisible();
    
    // Should show sample data note
    await expect(page.locator('.data-note-title')).toContainText('Sample Data Information');
  });

  test('should work with known sample races', async ({ page }) => {
    // Test with mo-senate-2024 which should work either way
    await page.goto('/races/mo-senate-2024');
    
    await page.waitForSelector('h1');
    
    // Should show the race title
    await expect(page.locator('h1')).toContainText('Senate Race');
    
    // Should show candidates
    await expect(page.locator('.candidate-grid')).toBeVisible();
  });
});
