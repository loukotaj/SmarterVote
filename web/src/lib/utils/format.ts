/** Display-friendly name for an AI model identifier. */
const MODEL_NAMES: Record<string, string> = {
  // OpenAI GPT-5 family
  "gpt-5.4": "GPT-5 Full",
  "gpt-5.4-mini": "GPT-5 Mini",
  "gpt-5-nano": "GPT-5 Nano",
  // OpenAI legacy
  "gpt-4o": "GPT-4o",
  "gpt-4o-mini": "GPT-4o Mini",
  "gpt-4": "GPT-4",
  "gpt-4-turbo": "GPT-4 Turbo",
  // Anthropic Claude 4
  "claude-sonnet-4-6": "Claude Sonnet 4.6",
  "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
  // Legacy Claude
  "claude-sonnet-4-20250514": "Claude Sonnet 4",
  "claude-haiku-4-20250514": "Claude Haiku 4",
  // Google Gemini 3
  "gemini-3-flash-preview": "Gemini 3 Flash",
  "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite",
  // Legacy Gemini
  "gemini-2.0-flash": "Gemini 2.0 Flash",
  "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
  // Grok
  "grok-3": "Grok 3",
  "grok-3-mini": "Grok 3 Mini",
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
