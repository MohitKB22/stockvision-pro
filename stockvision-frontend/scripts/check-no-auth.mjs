/**
 * Regression guard: assert the frontend's authentication code has not returned.
 *
 * Checks IMPORT SPECIFIERS and identifier usage rather than raw text, because the
 * source deliberately documents the removed subsystem in comments — a naive text
 * search matches those and fails the build for describing history accurately.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const FORBIDDEN_IMPORTS = [
  "@/store/auth-store",
  "@/hooks/use-auth",
  "@/lib/auto-auth",
  "@/components/layout/auth-guard",
];
const FORBIDDEN_IDENTIFIERS = ["useAuthStore", "useAuth", "AuthGuard", "ensureAuthenticated"];

function walk(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full);
    return /\.(ts|tsx)$/.test(entry) ? [full] : [];
  });
}

const findings = [];
for (const file of walk("src")) {
  // Strip comments so prose about the removal is not matched.
  const code = readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  code.split("\n").forEach((line, index) => {
    for (const spec of FORBIDDEN_IMPORTS) {
      if (line.includes(`"${spec}"`) || line.includes(`'${spec}'`)) {
        findings.push(`${file}:${index + 1}: imports ${spec}`);
      }
    }
    for (const name of FORBIDDEN_IDENTIFIERS) {
      if (new RegExp(`\\b${name}\\s*[(<]`).test(line)) {
        findings.push(`${file}:${index + 1}: uses ${name}`);
      }
    }
  });
}

if (findings.length) {
  console.error("Authentication code found — it was removed in v2.0:\n");
  findings.forEach((f) => console.error(`  ${f}`));
  process.exit(1);
}
console.log("Clean: no authentication code in the frontend.");
