import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescriptConfig from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier";

/**
 * ESLint flat config.
 *
 * `eslint-config-next` v16 ships NATIVE flat configs, so these are imported
 * directly. The FlatCompat shim (`@eslint/eslintrc`) that older Next.js
 * templates use throws `TypeError: Converting circular structure to JSON`
 * against v16 — it tries to serialise a config that now contains circular plugin
 * references. Importing the real exports is both correct and faster to load.
 *
 * `prettier` is last so formatting rules never fight the formatter.
 */
export default [
  ...coreWebVitals,
  ...typescriptConfig,
  prettier,
  {
    rules: {
      // An unused variable is nearly always a leftover or a bug; the underscore
      // prefix is the explicit opt-out.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      // `any` disables the type checking this project relies on.
      "@typescript-eslint/no-explicit-any": "error",
      // Error, not warn: a missing dependency here is a stale-closure bug that
      // reproduces intermittently and is very hard to track down.
      "react-hooks/exhaustive-deps": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
  {
    /**
     * React Compiler cannot memoize components that consume TanStack Table or
     * React Hook Form: both return freshly-bound functions on every render, so
     * the compiler skips optimizing the component rather than risk stale UI.
     *
     * An accepted trade-off, documented rather than hidden:
     *   - DataTable operates on at most 500 rows (the API's hard page cap), so
     *     the un-memoized render is already cheap.
     *   - NewOrderDialog is mounted only while open and re-renders per keystroke
     *     by design, to keep its live order-value preview in step.
     *
     * Scoped per-file, so a NEW component that trips this rule still surfaces it.
     */
    files: ["src/components/ui/data-table.tsx", "src/components/portfolio/new-order-dialog.tsx"],
    rules: { "react-hooks/incompatible-library": "off" },
  },
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts", "public/**"] },
];
