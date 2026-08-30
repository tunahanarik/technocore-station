import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

// Browser storage is banned outright in this app. The CSRF value must live in
// memory only (SI-24), and nothing else here is worth persisting; forbidding
// the APIs entirely makes the rule mechanical instead of a review habit.
const BANNED_STORAGE = [
  { name: "localStorage", message: "Browser storage is banned. Keep state in memory (SI-24)." },
  { name: "sessionStorage", message: "Browser storage is banned. Keep state in memory (SI-24)." },
  { name: "indexedDB", message: "Browser storage is banned. Keep state in memory (SI-24)." },
];

export default tseslint.config(
  { ignores: ["dist", "node_modules", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        project: ["./tsconfig.app.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-globals": ["error", ...BANNED_STORAGE],
      "no-restricted-properties": [
        "error",
        ...BANNED_STORAGE.map((entry) => ({
          object: "window",
          property: entry.name,
          message: entry.message,
        })),
      ],
      // Technocore content is untrusted data, never markup (AC-17).
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "Never render untrusted content as HTML (AC-17).",
        },
      ],
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}", "src/test/**/*.ts"],
    rules: {
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
