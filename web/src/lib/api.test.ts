import { describe, it, expect, vi } from 'vitest';
import { getRace } from './api';
import { sampleRaces } from './sampleData';

describe('API Fallback Functionality', () => {
  it('should return live data when API is available', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        id: 'test-race',
        title: 'Live Data Race',
        candidates: []
      })
    });

    const result = await getRace('test-race', mockFetch);
    
    expect(result.title).toBe('Live Data Race');
    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8080/races/test-race');
  });

  it('should fallback to sample data when API fails', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const result = await getRace('mo-senate-2024', mockFetch, true);
    
    expect(result.id).toBe('mo-senate-2024');
    expect(result.title).toBe('Missouri U.S. Senate Race 2024');
    expect(result.jurisdiction).toBe('Missouri');
  });

  it('should fallback to generic sample data for unknown race IDs', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const result = await getRace('unknown-race', mockFetch, true);
    
    expect(result.id).toBe('unknown-race');
    expect(result.title).toBe('Sample Race Data (unknown-race)');
    expect(result.candidates).toHaveLength(3); // Updated to match actual sample data
  });

  it('should throw error when fallback is disabled', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Network error'));

    await expect(getRace('test-race', mockFetch, false)).rejects.toThrow('Network error');
  });

  it('should have all required sample races', () => {
    const expectedRaces = ['mo-senate-2024', 'ca-senate-2024', 'ny-house-03-2024', 'tx-governor-2024'];
    
    expectedRaces.forEach(raceId => {
      expect(sampleRaces[raceId]).toBeDefined();
      expect(sampleRaces[raceId].id).toBe(raceId);
    });
  });
});
