/**
 * Capture real dashboard screenshots with puppeteer-core + local Chrome.
 * Seeds the frontend settings so the UI talks to the in-cluster platform API.
 *
 * Usage:
 *   node tools/capture-screenshots.js <platformApiBase> <token>
 *   node tools/capture-screenshots.js http://localhost:18080/platform <token>
 */
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer-core");

const CHROME =
  process.env.CHROME_PATH ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const APP = process.env.APP_URL || "http://localhost:18080";
const API_BASE = process.argv[2] || "http://localhost:18080/platform";
const TOKEN = process.argv[3] || "platform-demo-token";
const OUT = path.resolve(__dirname, "..", "screenshots");
const STORAGE_KEY = "gitops-platform.settings.v1";

const shots = [
  ["01-dashboard-overview.png", "/ops", 12000],
  ["02-pods.png", "/ops/pods", 6000],
  ["03-gitops-status.png", "/ops/gitops", 6000],
  ["04-monitoring.png", "/ops/monitoring", 8000],
  ["05-security.png", "/ops/security", 6000],
  ["06-deployments.png", "/ops/deployments", 6000],
  ["07-storefront.png", "/store", 8000],
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox", "--disable-gpu", "--hide-scrollbars"],
    defaultViewport: { width: 1600, height: 1100, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.error("pageerror:", e.message));

  await page.goto(APP, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.evaluate(
    (key, cfg) => window.localStorage.setItem(key, JSON.stringify(cfg)),
    STORAGE_KEY,
    { apiBase: API_BASE, gatewayBase: "http://localhost:18080/gateway", token: TOKEN }
  );

  for (const [file, route, wait] of shots) {
    const url = `${APP}${route}`;
    try {
      await page.goto(url, { waitUntil: "networkidle2", timeout: 45000 });
      await new Promise((r) => setTimeout(r, wait));
      await page.screenshot({ path: path.join(OUT, file) });
      console.log(`captured ${file}`);
    } catch (err) {
      console.error(`FAILED ${file}: ${err.message}`);
    }
  }

  // External UIs (Grafana, Prometheus) are served by port-forward.
  const external = [
    ["08-grafana-dashboard.png", process.env.GRAFANA_URL, 6000],
    ["09-prometheus-targets.png", process.env.PROMETHEUS_URL, 5000],
  ];
  for (const [file, url, wait] of external) {
    if (!url) continue;
    try {
      await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });
      await new Promise((r) => setTimeout(r, wait));
      await page.screenshot({ path: path.join(OUT, file) });
      console.log(`captured ${file}`);
    } catch (err) {
      console.error(`FAILED ${file}: ${err.message}`);
    }
  }

  await browser.close();
})();

