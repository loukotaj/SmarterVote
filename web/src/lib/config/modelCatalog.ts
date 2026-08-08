// GENERATED FILE -- DO NOT EDIT.
// Source: shared/model_catalog.py
// Regenerate: python scripts/generate_model_catalog_ts.py
//
// The frontend used to keep its own hand-written copy of these facts, which
// drifted onto models the pipeline had already retired. Change the Python
// catalog and re-run the generator instead.

export interface ModelSpec {
  id: string;
  label: string;
  inputPerM: number;
  outputPerM: number;
  cachedInputPerM: number | null;
  contextWindowTokens: number;
  intelligence: number;
  maxCompletionTokens: number | null;
}

export const MODEL_CATALOG: Record<string, ModelSpec> = {
  "openai/gpt-5.6-luna": {
    "id": "openai/gpt-5.6-luna",
    "label": "GPT-5.6 Luna",
    "inputPerM": 0.1,
    "outputPerM": 0.6,
    "cachedInputPerM": 0.01,
    "contextWindowTokens": 1050000,
    "intelligence": 51.2,
    "maxCompletionTokens": 128000
  },
  "openai/gpt-5.6-terra": {
    "id": "openai/gpt-5.6-terra",
    "label": "GPT-5.6 Terra",
    "inputPerM": 1.0,
    "outputPerM": 6.0,
    "cachedInputPerM": 0.1,
    "contextWindowTokens": 1050000,
    "intelligence": 55.0,
    "maxCompletionTokens": 128000
  },
  "openai/gpt-5.6-sol": {
    "id": "openai/gpt-5.6-sol",
    "label": "GPT-5.6 Sol",
    "inputPerM": 5.0,
    "outputPerM": 30.0,
    "cachedInputPerM": 0.5,
    "contextWindowTokens": 1050000,
    "intelligence": 58.9,
    "maxCompletionTokens": 128000
  },
  "deepseek/deepseek-v4-flash-0731": {
    "id": "deepseek/deepseek-v4-flash-0731",
    "label": "DeepSeek V4 Flash (07-31)",
    "inputPerM": 0.09,
    "outputPerM": 0.18,
    "cachedInputPerM": 0.018,
    "contextWindowTokens": 1048576,
    "intelligence": 49.9,
    "maxCompletionTokens": 65536
  },
  "deepseek/deepseek-v4-pro": {
    "id": "deepseek/deepseek-v4-pro",
    "label": "DeepSeek V4 Pro",
    "inputPerM": 0.435,
    "outputPerM": 0.87,
    "cachedInputPerM": 0.003625,
    "contextWindowTokens": 1048576,
    "intelligence": 44.3,
    "maxCompletionTokens": 384000
  },
  "google/gemini-3.1-flash-lite": {
    "id": "google/gemini-3.1-flash-lite",
    "label": "Gemini 3.1 Flash Lite",
    "inputPerM": 0.25,
    "outputPerM": 1.5,
    "cachedInputPerM": 0.025,
    "contextWindowTokens": 1048576,
    "intelligence": 25.0,
    "maxCompletionTokens": 65536
  },
  "google/gemini-3.5-flash-lite": {
    "id": "google/gemini-3.5-flash-lite",
    "label": "Gemini 3.5 Flash Lite",
    "inputPerM": 0.3,
    "outputPerM": 2.5,
    "cachedInputPerM": 0.03,
    "contextWindowTokens": 1048576,
    "intelligence": 36.5,
    "maxCompletionTokens": 65536
  },
  "google/gemini-3.6-flash": {
    "id": "google/gemini-3.6-flash",
    "label": "Gemini 3.6 Flash",
    "inputPerM": 1.5,
    "outputPerM": 7.5,
    "cachedInputPerM": 0.15,
    "contextWindowTokens": 1048576,
    "intelligence": 50.1,
    "maxCompletionTokens": 65536
  },
  "anthropic/claude-haiku-4.5": {
    "id": "anthropic/claude-haiku-4.5",
    "label": "Claude Haiku 4.5",
    "inputPerM": 1.0,
    "outputPerM": 5.0,
    "cachedInputPerM": 0.1,
    "contextWindowTokens": 200000,
    "intelligence": 24.0,
    "maxCompletionTokens": 64000
  },
  "anthropic/claude-sonnet-5": {
    "id": "anthropic/claude-sonnet-5",
    "label": "Claude Sonnet 5",
    "inputPerM": 2.0,
    "outputPerM": 10.0,
    "cachedInputPerM": 0.2,
    "contextWindowTokens": 1000000,
    "intelligence": 53.4,
    "maxCompletionTokens": 128000
  },
  "anthropic/claude-opus-5": {
    "id": "anthropic/claude-opus-5",
    "label": "Claude Opus 5",
    "inputPerM": 5.0,
    "outputPerM": 25.0,
    "cachedInputPerM": 0.5,
    "contextWindowTokens": 1000000,
    "intelligence": 60.7,
    "maxCompletionTokens": 128000
  },
  "x-ai/grok-4.3": {
    "id": "x-ai/grok-4.3",
    "label": "Grok 4.3",
    "inputPerM": 1.25,
    "outputPerM": 2.5,
    "cachedInputPerM": 0.2,
    "contextWindowTokens": 1000000,
    "intelligence": 37.6,
    "maxCompletionTokens": null
  },
  "x-ai/grok-4.5": {
    "id": "x-ai/grok-4.5",
    "label": "Grok 4.5",
    "inputPerM": 2.0,
    "outputPerM": 6.0,
    "cachedInputPerM": 0.3,
    "contextWindowTokens": 500000,
    "intelligence": 53.8,
    "maxCompletionTokens": null
  }
};

/** Display names, including models we have retired but still have runs for. */
export const MODEL_LABELS: Record<string, string> = {
  "openai/gpt-5.6-luna": "GPT-5.6 Luna",
  "openai/gpt-5.6-terra": "GPT-5.6 Terra",
  "openai/gpt-5.6-sol": "GPT-5.6 Sol",
  "deepseek/deepseek-v4-flash-0731": "DeepSeek V4 Flash (07-31)",
  "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
  "google/gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
  "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
  "google/gemini-3.6-flash": "Gemini 3.6 Flash",
  "anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
  "anthropic/claude-sonnet-5": "Claude Sonnet 5",
  "anthropic/claude-opus-5": "Claude Opus 5",
  "x-ai/grok-4.3": "Grok 4.3",
  "x-ai/grok-4.5": "Grok 4.5",
  "openai/gpt-5.4": "GPT-5.4",
  "openai/gpt-5.4-mini": "GPT-5.4 Mini",
  "openai/gpt-5-nano": "GPT-5 Nano",
  "anthropic/claude-sonnet-4.6": "Claude Sonnet 4.6",
  "google/gemini-3-flash-preview": "Gemini 3 Flash (Preview)",
  "google/gemini-3.1-pro-preview": "Gemini 3.1 Pro (Preview)",
  "google/gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite (Preview)",
  "google/gemini-3.5-flash": "Gemini 3.5 Flash",
  "google/gemini-2.5-flash": "Gemini 2.5 Flash",
  "x-ai/grok-4.20": "Grok 4.20",
  "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
  "deepseek/deepseek-chat-v3-0324": "DeepSeek V3 0324",
  "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super",
  "nvidia/nemotron-3-ultra-550b-a55b": "Nemotron 3 Ultra"
};

/** Old model IDs mapped onto their current equivalent. */
export const LEGACY_MODEL_ALIASES: Record<string, string> = {
  "gpt-5.6-luna": "openai/gpt-5.6-luna",
  "gpt-5.6-terra": "openai/gpt-5.6-terra",
  "gpt-5.6-sol": "openai/gpt-5.6-sol",
  "deepseek-v4-flash-0731": "deepseek/deepseek-v4-flash-0731",
  "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
  "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
  "claude-sonnet-5": "anthropic/claude-sonnet-5",
  "claude-opus-5": "anthropic/claude-opus-5",
  "gemini-3.1-flash-lite": "google/gemini-3.1-flash-lite",
  "gemini-3.5-flash-lite": "google/gemini-3.5-flash-lite",
  "gemini-3.6-flash": "google/gemini-3.6-flash",
  "grok-4.3": "x-ai/grok-4.3",
  "grok-4.5": "x-ai/grok-4.5",
  "openai/gpt-5.4": "openai/gpt-5.6-terra",
  "openai/gpt-5.4-mini": "openai/gpt-5.6-luna",
  "openai/gpt-5-nano": "openai/gpt-5.6-luna",
  "gpt-5.4": "openai/gpt-5.6-terra",
  "gpt-5.4-mini": "openai/gpt-5.6-luna",
  "gpt-5-nano": "openai/gpt-5.6-luna",
  "deepseek/deepseek-v4-flash": "deepseek/deepseek-v4-flash-0731",
  "deepseek-v4-flash": "deepseek/deepseek-v4-flash-0731",
  "deepseek/deepseek-chat-v3-0324": "deepseek/deepseek-v4-flash-0731",
  "deepseek-v3-0324": "deepseek/deepseek-v4-flash-0731",
  "anthropic/claude-sonnet-4.6": "anthropic/claude-sonnet-5",
  "claude-sonnet-4-6": "anthropic/claude-sonnet-5",
  "claude-3-5-sonnet-20241022": "anthropic/claude-sonnet-5",
  "claude-3-haiku-20240307": "anthropic/claude-haiku-4.5",
  "google/gemini-3.1-pro-preview": "google/gemini-3.6-flash",
  "gemini-3.1-pro-preview": "google/gemini-3.6-flash",
  "google/gemini-3-flash-preview": "google/gemini-3.6-flash",
  "gemini-3-flash-preview": "google/gemini-3.6-flash",
  "google/gemini-3.5-flash": "google/gemini-3.6-flash",
  "gemini-3.5-flash": "google/gemini-3.6-flash",
  "google/gemini-2.5-flash": "google/gemini-3.5-flash-lite",
  "gemini-2.5-flash": "google/gemini-3.5-flash-lite",
  "google/gemini-3.1-flash-lite-preview": "google/gemini-3.1-flash-lite",
  "gemini-3.1-flash-lite-preview": "google/gemini-3.1-flash-lite",
  "x-ai/grok-4.20": "x-ai/grok-4.3",
  "grok-4.20-0309-reasoning": "x-ai/grok-4.3",
  "grok-4-1-fast-non-reasoning": "x-ai/grok-4.3",
  "grok-3-mini": "x-ai/grok-4.3",
  "nvidia/nemotron-3-super-120b-a12b": "deepseek/deepseek-v4-flash-0731",
  "nvidia/nemotron-3-ultra-550b-a55b": "openai/gpt-5.6-terra",
  "nemotron-3-super": "deepseek/deepseek-v4-flash-0731",
  "nemotron-3-ultra": "openai/gpt-5.6-terra"
};

export const MODEL_PROFILES: string[] = [
  "custom",
  "default",
  "premium"
];

export const PROFILE_DEFAULTS: Record<string, Record<string, string>> = {
  "default": {
    "primary": "deepseek/deepseek-v4-flash-0731",
    "small": "openai/gpt-5.6-luna",
    "roster": "deepseek/deepseek-v4-flash-0731",
    "review_claude": "anthropic/claude-haiku-4.5",
    "review_gemini": "google/gemini-3.5-flash-lite",
    "review_grok": "x-ai/grok-4.3"
  },
  "premium": {
    "primary": "openai/gpt-5.6-terra",
    "small": "openai/gpt-5.6-luna",
    "roster": "openai/gpt-5.6-terra",
    "review_claude": "anthropic/claude-sonnet-5",
    "review_gemini": "google/gemini-3.6-flash",
    "review_grok": "x-ai/grok-4.5"
  }
};

export const DEFAULT_CHAMBER_FORECAST_MODEL = "google/gemini-3.6-flash";

export type ReviewerKey = "claude" | "gemini" | "grok";

export const REVIEWER_DEFS: {
  key: ReviewerKey;
  name: string;
  options: { value: string; label: string }[];
}[] = [
  {
    "key": "claude",
    "name": "Claude",
    "options": [
      {
        "value": "anthropic/claude-haiku-4.5",
        "label": "Claude Haiku 4.5"
      },
      {
        "value": "anthropic/claude-sonnet-5",
        "label": "Claude Sonnet 5"
      }
    ]
  },
  {
    "key": "gemini",
    "name": "Gemini",
    "options": [
      {
        "value": "google/gemini-3.5-flash-lite",
        "label": "Gemini 3.5 Flash Lite"
      },
      {
        "value": "google/gemini-3.6-flash",
        "label": "Gemini 3.6 Flash"
      }
    ]
  },
  {
    "key": "grok",
    "name": "Grok",
    "options": [
      {
        "value": "x-ai/grok-4.3",
        "label": "Grok 4.3"
      },
      {
        "value": "x-ai/grok-4.5",
        "label": "Grok 4.5"
      }
    ]
  }
];

export const RESEARCH_MODELS: { value: string; label: string }[] = [
  {
    "value": "",
    "label": "Auto (profile selects)"
  },
  {
    "value": "deepseek/deepseek-v4-flash-0731",
    "label": "DeepSeek V4 Flash (07-31) (default)"
  },
  {
    "value": "openai/gpt-5.6-terra",
    "label": "GPT-5.6 Terra (premium)"
  }
];

export const DEFAULT_REVIEWER_MODELS: Record<ReviewerKey, string> = {
  "claude": "anthropic/claude-haiku-4.5",
  "gemini": "google/gemini-3.5-flash-lite",
  "grok": "x-ai/grok-4.3"
};
