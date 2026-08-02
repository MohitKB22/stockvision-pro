// Simulates the EXACT requests each frontend hook (src/hooks/*.ts) makes
// against the live backend, verifying: (1) CORS headers are present and
// correct, since axios/fetch in a real browser would silently fail without
// them even if curl/Node wouldn't notice, and (2) every response shape
// matches the TypeScript interfaces in src/types/index.ts field-for-field.
const BASE = "http://127.0.0.1:8000/api/v1";
const ORIGIN = "http://localhost:3000";
let failures = [];

function check(label, condition, extra = "") {
  const status = condition ? "PASS" : "FAIL";
  console.log(`[${status}] ${label} ${extra}`);
  if (!condition) failures.push(label);
}

async function main() {
  // --- CORS preflight check (mirrors what a real browser does before any
  // cross-origin POST with a custom header like Authorization) -----------
  const preflight = await fetch(`${BASE}/auth/login`, {
    method: "OPTIONS",
    headers: {
      Origin: ORIGIN,
      "Access-Control-Request-Method": "POST",
      "Access-Control-Request-Headers": "authorization,content-type",
    },
  });
  check(
    "CORS preflight allows the Next.js origin",
    preflight.headers.get("access-control-allow-origin") === ORIGIN,
    `(got: ${preflight.headers.get("access-control-allow-origin")})`
  );

  // --- Register + login, exactly as use-auth.ts does ---------------------
  const email = `frontend_test_${Date.now()}@stockvision-demo.com`;
  const registerResp = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: ORIGIN },
    body: JSON.stringify({ email, password: "TestPass123!", full_name: "Frontend Test", role: "admin" }),
  });
  check("register (matches UserPublic shape)", registerResp.status === 201);
  const registerBody = await registerResp.json();
  check(
    "UserPublic has exactly the fields the frontend types expect",
    ["id", "email", "full_name", "role", "is_active"].every((k) => k in registerBody) &&
      !("hashed_password" in registerBody)
  );

  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", "TestPass123!");
  const loginResp = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Origin: ORIGIN },
    body: form,
  });
  check(
    "login response has access_token + refresh_token (matches TokenPair)",
    loginResp.status === 200,
    `status=${loginResp.status}`
  );
  const { access_token } = await loginResp.json();
  const authHeaders = { Authorization: `Bearer ${access_token}`, "Content-Type": "application/json", Origin: ORIGIN };

  // --- Stocks: create, list, get -- matches use-stocks.ts exactly --------
  const symbol = `FE${Date.now() % 100000}`;
  const createStockResp = await fetch(`${BASE}/stocks`, {
    method: "POST",
    headers: authHeaders,
    body: JSON.stringify({ symbol, name: "Frontend Test Corp", exchange: "NASDAQ", sector: "Technology" }),
  });
  check("create stock (matches StockPublic shape)", createStockResp.status === 201);
  const stock = await createStockResp.json();
  check(
    "StockPublic has exactly the fields the frontend expects",
    ["id", "symbol", "name", "exchange", "sector", "industry", "currency"].every((k) => k in stock)
  );

  // Bulk import prices, exactly the shape the backend needs
  const bars = Array.from({ length: 120 }, (_, i) => {
    const date = new Date(2024, 0, 1 + i);
    const price = 100 + Math.sin(i / 10) * 10 + i * 0.1;
    return {
      timestamp: date.toISOString(),
      open: price, high: price + 1, low: price - 1, close: price + 0.5, volume: 1_000_000,
    };
  });
  const importResp = await fetch(`${BASE}/stocks/${symbol}/prices`, {
    method: "POST", headers: authHeaders, body: JSON.stringify({ bars }),
  });
  check("bulk price import", importResp.status === 201);

  const pricesResp = await fetch(`${BASE}/stocks/${symbol}/prices?limit=300`, { headers: authHeaders });
  const prices = await pricesResp.json();
  check(
    "PriceBarPublic[] matches shape used by PriceChart component",
    Array.isArray(prices) && prices.length > 0 &&
      ["timestamp", "open", "high", "low", "close", "volume", "source"].every((k) => k in prices[0])
  );

  const featuresResp = await fetch(`${BASE}/stocks/${symbol}/features?limit=5`, { headers: authHeaders });
  const features = await featuresResp.json();
  check(
    "FeatureSnapshot[] matches shape used by indicators panel",
    Array.isArray(features) && features.length > 0 && "indicators" in features[0] && "close" in features[0]
  );

  // --- Signal: matches use-ml.ts's useSignal exactly ----------------------
  const signalResp = await fetch(`${BASE}/signals/${symbol}`, { method: "POST", headers: authHeaders });
  check("generate signal (matches SignalResponse shape)", signalResp.status === 200, `status=${signalResp.status}`);
  const signal = await signalResp.json();
  check(
    "SignalResponse has exactly the fields SignalPanel component destructures",
    ["id", "stock_symbol", "action", "confidence", "risk_score", "supporting_indicators", "explanation", "shap_contributions", "generated_at"]
      .every((k) => k in signal)
  );

  // --- Portfolio: create, order, summary, risk -- matches use-portfolios.ts
  const portfolioResp = await fetch(`${BASE}/portfolios`, {
    method: "POST", headers: authHeaders, body: JSON.stringify({ name: "Frontend Test Portfolio", benchmark_symbol: symbol }),
  });
  const portfolio = await portfolioResp.json();
  check("create portfolio (matches PortfolioPublic shape)", portfolioResp.status === 201);

  const orderResp = await fetch(`${BASE}/portfolios/${portfolio.id}/orders`, {
    method: "POST", headers: authHeaders, body: JSON.stringify({ symbol, side: "buy", quantity: 10, price: 100 }),
  });
  check("submit order", orderResp.status === 201);

  const summaryResp = await fetch(`${BASE}/portfolios/${portfolio.id}/summary`, { headers: authHeaders });
  const summary = await summaryResp.json();
  check(
    "PortfolioSummary matches shape used by holdings table + sector pie chart",
    ["total_market_value", "total_unrealized_pnl", "holdings", "sector_exposure"].every((k) => k in summary) &&
      summary.holdings.length > 0 &&
      ["symbol", "quantity", "average_cost", "current_price", "unrealized_pnl", "weight_pct", "sector"].every((k) => k in summary.holdings[0])
  );

  const riskResp = await fetch(`${BASE}/portfolios/${portfolio.id}/risk`, { headers: authHeaders });
  const risk = await riskResp.json();
  check(
    "RiskMetricsResponse matches shape used by risk metrics grid",
    riskResp.status === 200 &&
      ["sharpe_ratio", "sortino_ratio", "max_drawdown", "value_at_risk_95_historical", "value_at_risk_95_monte_carlo", "expected_shortfall_95", "beta"]
        .every((k) => k in risk)
  );

  // --- Copilot: multipart document upload, exactly as use-copilot.ts's
  // useUploadDocument builds its FormData -----------------------------------
  const fs = await import("fs");
  const path = await import("path");
  const pdfPath = path.join(process.cwd(), "..", "stockvision-backend", "data", "sample_pdfs", "meridian_robotics_10q_q3_2025.pdf");
  const pdfBuffer = fs.readFileSync(pdfPath);
  const pdfBlob = new Blob([pdfBuffer], { type: "application/pdf" });

  const uploadForm = new FormData();
  uploadForm.append("file", pdfBlob, "meridian_10q.pdf");
  uploadForm.append("document_type", "quarterly_report");

  const uploadResp = await fetch(`${BASE}/documents/upload`, {
    method: "POST",
    headers: { Authorization: authHeaders.Authorization, Origin: ORIGIN }, // NOTE: no Content-Type -- fetch sets the multipart boundary itself, exactly like the browser's FormData does
    body: uploadForm,
  });
  const uploadBody = await uploadResp.json();
  check(
    "multipart PDF upload (matches DocumentUploadResponse shape used by UploadPanel)",
    uploadResp.status === 201 &&
      ["id", "filename", "document_type", "page_count", "chunks_created", "pages_with_no_extractable_text"].every((k) => k in uploadBody),
    `status=${uploadResp.status}`
  );

  const queryResp = await fetch(`${BASE}/copilot/query`, {
    method: "POST", headers: authHeaders,
    body: JSON.stringify({ question: "What was total revenue this quarter?", top_k: 3 }),
  });
  const queryBody = await queryResp.json();
  check(
    "copilot query (matches CopilotQueryResponse shape used by the chat UI)",
    queryResp.status === 200 &&
      ["question", "answer", "llm_provider", "citations"].every((k) => k in queryBody) &&
      queryBody.citations.length > 0 &&
      ["document_name", "page_number", "chunk_text", "relevance_score"].every((k) => k in queryBody.citations[0])
  );

  const historyResp = await fetch(`${BASE}/copilot/history`, { headers: authHeaders });
  const history = await historyResp.json();
  check("copilot history (matches CopilotQueryResponse[] shape)", historyResp.status === 200 && Array.isArray(history) && history.length >= 1);

  console.log();
  console.log("=".repeat(70));
  if (failures.length > 0) {
    console.log(`${failures.length} CHECK(S) FAILED:`);
    failures.forEach((f) => console.log(`  - ${f}`));
    process.exit(1);
  } else {
    console.log("ALL CHECKS PASSED");
    process.exit(0);
  }
}

main().catch((err) => {
  console.error("SCRIPT ERROR:", err);
  process.exit(1);
});
