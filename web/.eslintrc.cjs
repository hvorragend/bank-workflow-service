/* ESLint-Konfiguration (S-006). Bewusst schlank gehalten: tsc bleibt die
 * primaere Typpruefung, ESLint ergaenzt v. a. React-Hooks-Regeln. Die meisten
 * Stilregeln laufen als "warn", damit der bestehende Code-Bestand den Build
 * nicht blockiert; nur die Rules-of-Hooks sind hart. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  plugins: ["@typescript-eslint", "react-hooks", "react-refresh"],
  ignorePatterns: [
    "dist",
    "node_modules",
    "*.config.ts",
    "*.config.js",
    "*.cjs",
  ],
  rules: {
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
    "no-unused-vars": "off",
    "@typescript-eslint/no-unused-vars": [
      "warn",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
    "no-undef": "off",
  },
};
