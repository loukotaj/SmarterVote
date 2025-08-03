import { expect, test } from '@playwright/test';

const mockRace = {
    id: 'test-race-123',
    title: 'Mayor of Example City',
    office: 'Mayor',
    jurisdiction: 'Example City',
    election_date: '2024-11-05',
    candidates: [
        {
            name: 'Jane Smith',
            party: 'Democratic',
            incumbent: true,
            website: 'https://janesmith.com',
            biography: 'Jane Smith has served as mayor for the past 4 years...',
            positions: [
                {
                    topic: 'Housing',
                    stance: 'Pro-affordable housing',
                    summary: 'Supports increasing affordable housing units by 20%',
                    confidence: 'high'
                },
                {
                    topic: 'Transportation',
                    stance: 'Pro-public transit',
                    summary: 'Plans to expand bus routes and bike lanes',
                    confidence: 'medium'
                }
            ]
        },
        {
            name: 'John Doe',
            party: 'Republican',
            incumbent: false,
            website: 'https://johndoe.com',
            biography: 'John Doe is a local business owner...',
            positions: [
                {
                    topic: 'Economic Development',
                    stance: 'Pro-business',
                    summary: 'Wants to reduce business taxes and regulations',
                    confidence: 'high'
                },
                {
                    topic: 'Public Safety',
                    stance: 'Increase police funding',
                    summary: 'Proposes hiring 50 additional police officers',
                    confidence: 'medium'
                }
            ]
        }
    ],
    description: 'The mayoral race for Example City',
    key_issues: ['Housing', 'Transportation', 'Economic Development', 'Public Safety']
};

test.beforeEach(async ({ page }) => {
    await page.route('**/races/test-race-123', route => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockRace)
        });
    });
});

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
