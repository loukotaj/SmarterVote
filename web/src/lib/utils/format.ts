/** Display-friendly name for an AI model identifier. */
const MODEL_NAMES: Record<string, string> = {
  // OpenRouter GPT-5 family
  "openai/gpt-5.4": "GPT-5.4",
  "openai/gpt-5.4-mini": "GPT-5.4 Mini",
  "openai/gpt-5-nano": "GPT-5 Nano",
  "gpt-5.4": "GPT-5 Full",
  "gpt-5.4-mini": "GPT-5 Mini",
  "gpt-5-nano": "GPT-5 Nano",
  // Legacy OpenAI IDs
  "gpt-4o": "GPT-4o",
  "gpt-4o-mini": "GPT-4o Mini",
  "gpt-4": "GPT-4",
  "gpt-4-turbo": "GPT-4 Turbo",
  // OpenRouter Claude models
  "anthropic/claude-sonnet-4.6": "Claude Sonnet 4.6",
  "anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
  "claude-sonnet-4-6": "Claude Sonnet 4.6",
  "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
  // Legacy Claude
  "claude-sonnet-4-20250514": "Claude Sonnet 4",
  "claude-haiku-4-20250514": "Claude Haiku 4",
  // OpenRouter Gemini models
  "google/gemini-3-flash-preview": "Gemini 3 Flash",
  "google/gemini-3.1-pro-preview": "Gemini 3.1 Pro",
  "google/gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite",
  "google/gemini-3.5-flash": "Gemini 3.5 Flash",
  "gemini-3-flash-preview": "Gemini 3 Flash",
  "gemini-3.1-pro-preview": "Gemini 3.1 Pro",
  "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite",
  "gemini-3.5-flash": "Gemini 3.5 Flash",
  // Legacy Gemini
  "gemini-2.0-flash": "Gemini 2.0 Flash",
  "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
  // OpenRouter Grok models
  "x-ai/grok-4.20": "Grok 4.20",
  "x-ai/grok-4.3": "Grok 4.3",
  "grok-3": "Grok 3",
  "grok-3-mini": "Grok 3 Mini",
  "grok-4.20-0309-reasoning": "Grok 4.20 Reasoning",
  "grok-4-1-fast-non-reasoning": "Grok 4.3",
  // Internal pipeline tags
  "pipeline-agent": "GPT-4o Mini",
  "pipeline-v2-agent": "GPT-4o Mini",
};

export function formatModelName(raw: string): string {
  return MODEL_NAMES[raw] ?? raw;
}

/** Turn a candidate name into a URL-safe slug. */
export function candidateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}
