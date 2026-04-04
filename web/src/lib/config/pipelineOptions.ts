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
      { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
      { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
    ],
  },
  {
    key: "gemini",
    name: "Gemini",
    options: [
      { value: "gemini-3-flash-preview", label: "Gemini 3 Flash" },
      { value: "gemini-3.1-flash-lite-preview", label: "Gemini 3.1 Flash Lite" },
    ],
  },
  {
    key: "grok",
    name: "Grok",
    options: [
      { value: "grok-3", label: "Grok 3" },
      { value: "grok-3-mini", label: "Grok 3 mini" },
    ],
  },
];

export const RESEARCH_MODELS = [
  { value: "", label: "Auto (cheap mode selects)" },
  { value: "gpt-5.4", label: "GPT-5.4 — best quality" },
  { value: "gpt-5.4-mini", label: "GPT-5.4 mini — fast & smart" },
  { value: "gpt-5-nano", label: "GPT-5 nano — fastest & cheapest" },
];

export function createDefaultReviewerEnabled(): Record<ReviewerKey, boolean> {
  return { claude: false, gemini: false, grok: false };
}

export function createDefaultReviewerModels(): Record<ReviewerKey, string> {
  return {
    claude: "claude-sonnet-4-6",
    gemini: "gemini-3-flash-preview",
    grok: "grok-3",
  };
}

export function applyReviewerModelOptions(
  opts: RunOptions,
  reviewerEnabled: Record<ReviewerKey, boolean>,
  reviewerModels: Record<ReviewerKey, string>
): RunOptions {
  if (reviewerEnabled.claude) opts.claude_model = reviewerModels.claude;
  if (reviewerEnabled.gemini) opts.gemini_model = reviewerModels.gemini;
  if (reviewerEnabled.grok) opts.grok_model = reviewerModels.grok;
  return opts;
}
