/**
 * TypeScript definitions for SmarterVote RaceJSON v0.2
 */

export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'unknown';

export type CanonicalIssue = 
  | 'Healthcare'
  | 'Economy'
  | 'Climate/Energy'
  | 'Reproductive Rights'
  | 'Immigration'
  | 'Guns & Safety'
  | 'Foreign Policy'
  | 'LGBTQ+ Rights'
  | 'Education'
  | 'Tech & AI'
  | 'Election Reform';

export interface IssueStance {
  stance: string;
  confidence: ConfidenceLevel;
  sources: string[];
}

export interface TopDonor {
  name: string;
  amount?: number;
  organization?: string;
  source: string;
}

export interface Candidate {
  name: string;
  party?: string;
  incumbent: boolean;
  summary: string;
  issues: Record<CanonicalIssue, IssueStance>;
  top_donors: TopDonor[];
  website?: string;
  social_media: Record<string, string>;
}

export interface Race {
  id: string;
  election_date: string;
  candidates: Candidate[];
  updated_utc: string;
  generator: string[];
  title?: string;
  office?: string;
  jurisdiction?: string;
}

export const CANONICAL_ISSUES: CanonicalIssue[] = [
  'Healthcare',
  'Economy', 
  'Climate/Energy',
  'Reproductive Rights',
  'Immigration',
  'Guns & Safety',
  'Foreign Policy',
  'LGBTQ+ Rights',
  'Education',
  'Tech & AI',
  'Election Reform'
];
