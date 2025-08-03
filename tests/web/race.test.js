import { expect, test } from '@playwright/test';

test('race page loads correctly', async ({ page }) => {
	await page.goto('/races/test-race-123');
	
	// Check that the page loads
	await expect(page).toHaveTitle(/SmarterVote/);
	
	// Check for race title
	await expect(page.locator('h1')).toContainText('Mayor of Example City');
	
	// Check for candidates
	await expect(page.locator('text=Jane Smith')).toBeVisible();
	await expect(page.locator('text=John Doe')).toBeVisible();
	
	// Check for key issues
	await expect(page.locator('text=Key Issues')).toBeVisible();
	await expect(page.locator('text=Housing')).toBeVisible();
});

test('candidate information displays correctly', async ({ page }) => {
	await page.goto('/races/test-race-123');
	
	// Check for incumbent badge
	await expect(page.locator('text=Incumbent')).toBeVisible();
	
	// Check for party affiliation
	await expect(page.locator('text=Democratic')).toBeVisible();
	await expect(page.locator('text=Republican')).toBeVisible();
	
	// Check for positions
	await expect(page.locator('text=Pro-affordable housing')).toBeVisible();
	await expect(page.locator('text=Pro-business')).toBeVisible();
});

test('confidence indicators work', async ({ page }) => {
	await page.goto('/races/test-race-123');
	
	// Check for confidence indicators
	await expect(page.locator('text=high confidence')).toBeVisible();
	await expect(page.locator('text=medium confidence')).toBeVisible();
});
