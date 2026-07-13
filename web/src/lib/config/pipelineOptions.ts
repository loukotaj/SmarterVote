import type { RunOptions } from "$lib/types";

export type ReviewerKey = "claude" | "gemini" | "grok";

export const REVIEWER_DEFS: {
  key: ReviewerKey;
  name: string;
  options: { value: string; label: string }[];
}[] = [
  {
    key: "claude",
    name: "Claude",
    options: [
      { value: "anthropic/claude-sonnet-4.6", label: "Claude Sonnet 4.6" },
      { value: "anthropic/claude-haiku-4.5", label: "Claude Haiku 4.5" },
    ],
  },
  {
    key: "gemini",
    name: "Gemini",
    options: [
      {
        value: "google/gemini-3.1-pro-preview",
        label: "Gemini 3.1 Pro (Preview)",
      },
      {
        value: "google/gemini-3.1-flash-lite-preview",
        label: "Gemini 3.1 Flash Lite",
      },
    ],
  },
  {
    key: "grok",
    name: "Grok",
    options: [
      { value: "x-ai/grok-4.20", label: "Grok 4.20" },
      { value: "x-ai/grok-4.3", label: "Grok 4.3" },
    ],
  },
];

export const RESEARCH_MODELS = [
  { value: "", label: "Auto (profile selects)" },
  { value: "openai/gpt-5.4", label: "GPT-5.4 - best quality" },
  { value: "openai/gpt-5.4-mini", label: "GPT-5.4 mini - fast & smart" },
  {
    value: "openai/gpt-5-nano",
    label: "GPT-5 nano - advanced low-cost override",
  },
];

export function createDefaultReviewerEnabled(
  reviewEnabled: boolean = false,
): Record<ReviewerKey, boolean> {
  if (reviewEnabled) {
    return { claude: true, gemini: true, grok: true };
  }
  return { claude: false, gemini: false, grok: false };
}

export function createDefaultReviewerModels(): Record<ReviewerKey, string> {
  return {
    claude: "anthropic/claude-haiku-4.5",
    gemini: "google/gemini-3.1-flash-lite-preview",
    grok: "x-ai/grok-4.3",
  };
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
