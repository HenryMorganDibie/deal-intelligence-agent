// ESLint 9 flat config (Next 16 removed `next lint`), on Next's core web vitals set.
//
// Next 16's set adds the React Compiler rules. Patterns they flag (setting state inside an effect, Date.now() during
// render) work as written today, so they are warnings to clean up, not build failures. no-html-link-for-pages stays
// off as it effectively was under Next 14 (it only looked at a pages/ directory): some plain links do a full page
// load on purpose.
import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextVitals,
  {
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/purity": "warn",
      "@next/next/no-html-link-for-pages": "off",
    },
  },
  { ignores: [".next/**", "node_modules/**", ".test-build/**", "next-env.d.ts", "public/**", "test-results/**"] },
];

export default config;
