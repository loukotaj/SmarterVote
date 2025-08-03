import { expect, test } from '@playwright/test';

const mockRace = {
  id: 'test-race-123',
  title: 'Mayor of Example City',
  office: 'Mayor',
  jurisdiction: 'Example City',
  election_date: '2024-11-05',
  updated_utc: '2024-10-15T10:30:00Z',
  generator: ['GPT-4', 'Claude'],
  candidates: [
    {
      name: 'Jane Smith',
      party: 'Democratic',
      incumbent: true,
      website: 'https://janesmith.com',
      social_media: {},
      summary: 'Current mayor with 8 years of experience in local government.',
      top_donors: [],
      issues: {
        Healthcare: { stance: 'Supports expanding community health programs.', confidence: 'high', sources: [] },
        Economy: { stance: 'Pro-affordable Housing', confidence: 'high', sources: [] },
        'Climate/Energy': { stance: '', confidence: 'low', sources: [] },
        'Reproductive Rights': { stance: '', confidence: 'low', sources: [] },
        Immigration: { stance: '', confidence: 'low', sources: [] },
        'Guns & Safety': { stance: '', confidence: 'low', sources: [] },
        'Foreign Policy': { stance: '', confidence: 'low', sources: [] },
        'LGBTQ+ Rights': { stance: '', confidence: 'low', sources: [] },
        Education: { stance: '', confidence: 'low', sources: [] },
        'Tech & AI': { stance: '', confidence: 'low', sources: [] },
        'Election Reform': { stance: '', confidence: 'low', sources: [] }
      }
    },
    {
      name: 'John Doe',
      party: 'Republican',
      incumbent: false,
      website: 'https://johndoe.com',
      social_media: {},
      summary: 'Local business owner focused on economic development and public safety.',
      top_donors: [],
      issues: {
        Healthcare: { stance: '', confidence: 'low', sources: [] },
        Economy: { stance: 'Pro-business', confidence: 'medium', sources: [] },
        'Climate/Energy': { stance: '', confidence: 'low', sources: [] },
        'Reproductive Rights': { stance: '', confidence: 'low', sources: [] },
        Immigration: { stance: '', confidence: 'low', sources: [] },
        'Guns & Safety': { stance: '', confidence: 'low', sources: [] },
        'Foreign Policy': { stance: '', confidence: 'low', sources: [] },
        'LGBTQ+ Rights': { stance: '', confidence: 'low', sources: [] },
        Education: { stance: '', confidence: 'low', sources: [] },
        'Tech & AI': { stance: '', confidence: 'low', sources: [] },
        'Election Reform': { stance: '', confidence: 'low', sources: [] }
      }
    }
  ]
};

test.beforeEach(async ({ page }) => {
  await page.route('**/races/test-race-123', route => {
    route.fulfill({ json: mockRace });
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
  await expect(page.locator('text=Pro-affordable Housing')).toBeVisible();
  await expect(page.locator('text=Pro-business')).toBeVisible();
});

test('confidence indicators work', async ({ page }) => {
  await page.goto('/races/test-race-123');

  // Check for confidence indicators
  await expect(page.locator('text=high confidence')).toBeVisible();
  await expect(page.locator('text=medium confidence')).toBeVisible();
});
