module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:svelte/recommended",
    "prettier",
  ],
  plugins: ["@typescript-eslint"],
  ignorePatterns: [
    "build/**",
    ".svelte-kit/**",
    "node_modules/**",
    "Smarter.Vote visual system/**",
  ],
  env: {
    browser: true,
    node: true,
    es2020: true,
  },
  parserOptions: {
    sourceType: "module",
    ecmaVersion: 2020,
  },
  rules: {
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/no-unused-vars": [
      "error",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
    "no-useless-escape": "warn",
  },
  overrides: [
    {
      files: ["*.svelte"],
      parser: "svelte-eslint-parser",
      parserOptions: {
        parser: "@typescript-eslint/parser",
      },
      rules: {
        "@typescript-eslint/no-unused-expressions": "off",
        "@typescript-eslint/no-unused-vars": [
          "error",
          {
            argsIgnorePattern: "^_",
            varsIgnorePattern: "^_",
            caughtErrors: "none",
          },
        ],
      },
    },
    {
      files: ["**/*.d.ts"],
      rules: {
        "@typescript-eslint/no-explicit-any": "off",
      },
    },
    {
      files: ["**/*.test.ts", "**/*.test.js"],
      rules: {
        "@typescript-eslint/no-explicit-any": "off",
      },
    },
  ],
};
