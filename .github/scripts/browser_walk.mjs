// Visits every page of a deployed frontend in headless Chromium and reports
// console errors, uncaught exceptions, failed API calls and visible error text.
//
//   node .github/scripts/browser_walk.mjs https://your-frontend.vercel.app [screenshot-dir]
//
// Exit code 0 = every page rendered cleanly. Run by .github/workflows/verify.yml.
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const BASE = (process.argv[2] || "http://localhost:3000").replace(/\/$/, "");
const OUT = process.argv[3] || "screenshots";
const PAGES = ["/dashboard", "/market", "/stocks/RELIANCE", "/portfolio", "/risk", "/prediction",
  "/news", "/watchlist", "/reports", "/settings", "/admin"];
const ERROR_TEXT = ["Cannot reach the API", "Something went wrong", "Application error", "NaN", "Invalid Date"];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 }, timezoneId: "Asia/Kolkata", locale: "en-IN",
});

let problems = 0;
for (const path of PAGES) {
  const page = await context.newPage();
  const issues = [];
  let apiCalls = 0;
  page.on("console", (m) => { if (m.type() === "error") issues.push(`console: ${m.text().slice(0, 200)}`); });
  page.on("pageerror", (e) => issues.push(`pageerror: ${String(e).slice(0, 200)}`));
  page.on("response", (r) => {
    if (!r.url().includes("/api/v1/")) return;
    apiCalls += 1;
    if (r.status() >= 400) issues.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(/^.*\/api\/v1/, "")}`);
  });
  page.on("requestfailed", (r) => {
    // Next.js link prefetches (?_rsc=) are cancelled when the page closes — not a fault.
    if (!r.url().includes("_rsc=")) issues.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`);
  });

  // A cold serverless function can take several seconds on the first call.
  await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 120_000 })
    .catch((e) => issues.push(`navigation: ${String(e).slice(0, 200)}`));
  await page.waitForTimeout(1500);
  const text = await page.locator("body").innerText().catch(() => "");
  for (const marker of ERROR_TEXT) if (text.includes(marker)) issues.push(`visible text: "${marker}"`);
  await page.screenshot({ path: `${OUT}/${path.replace(/\//g, "_").replace(/^_/, "")}.png` });

  console.log(`${issues.length ? "ISSUES" : "ok    "} ${path.padEnd(18)} api_calls=${apiCalls}`);
  for (const issue of issues) console.log(`         - ${issue}`);
  problems += issues.length;
  await page.close();
}
await browser.close();
console.log(`\n${PAGES.length} pages, ${problems} problem(s)`);
process.exit(problems ? 1 : 0);
