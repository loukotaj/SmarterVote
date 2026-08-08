import type { RunOptions } from "$lib/types";
import {
  DEFAULT_REVIEWER_MODELS,
  RESEARCH_MODELS,
  REVIEWER_DEFS,
  type ReviewerKey,
} from "$lib/config/modelCatalog";

// The model lists are generated from shared/model_catalog.py -- see
// scripts/generate_model_catalog_ts.py. They used to be written out by hand
// here, and went stale: the picker offered gpt-5.4, gemini-3.1-pro-preview and
// grok-4.20 for months after the pipeline stopped running any of them.
export { DEFAULT_REVIEWER_MODELS, RESEARCH_MODELS, REVIEWER_DEFS };
export type { ReviewerKey };

export function createDefaultReviewerEnabled(
  reviewEnabled: boolean = false,
): Record<ReviewerKey, boolean> {
  if (reviewEnabled) {
    return { claude: true, gemini: true, grok: true };
  }
  return { claude: false, gemini: false, grok: false };
}

export function createDefaultReviewerModels(): Record<ReviewerKey, string> {
  return { ...DEFAULT_REVIEWER_MODELS };
}

export function applyReviewerModelOptions(
  opts: RunOptions,
  reviewerEnabled: Record<ReviewerKey, boolean>,
  reviewerModels: Record<ReviewerKey, string>,
): RunOptions {
  opts.review_providers = REVIEWER_DEFS.map((reviewer) => reviewer.key).filter(
    (key) => reviewerEnabled[key],
  );
  if (reviewerEnabled.claude) opts.claude_model = reviewerModels.claude;
  if (reviewerEnabled.gemini) opts.gemini_model = reviewerModels.gemini;
  if (reviewerEnabled.grok) opts.grok_model = reviewerModels.grok;
  return opts;
}
