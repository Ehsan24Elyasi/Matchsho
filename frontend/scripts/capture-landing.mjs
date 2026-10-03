import fs from "node:fs";
import { chromium } from "@playwright/test";

const baseURL = process.env.BASE_URL || "http://localhost:8088";
const source = process.env.EVIDENCE_SOURCE || "published";
if (!["published", "static"].includes(source))
  throw new Error("EVIDENCE_SOURCE must be published or static");
const evidence = "../docs/pilot/evidence";
fs.mkdirSync(evidence, { recursive: true });
const browser = await chromium.launch();
try {
  for (const [width, height, label] of [[1280, 720, "desktop"], [390, 844, "mobile"]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    const failures = [];
    page.on("response", (response) => {
      if (response.status() >= 400) failures.push({ url: response.url(), status: response.status() });
    });
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    await page.goto(baseURL, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    // Include below-fold artwork as well as initial-viewport images in the budget.
    await page.evaluate(async () => {
      for (const image of document.images) image.loading = "eager";
      await Promise.all([...document.images].map((image) => image.decode()));
    });
    await page.screenshot({ path: `${evidence}/landing-${source}-${label}.png`, fullPage: true });
    const report = await page.evaluate(() => ({
      viewport: { width: innerWidth, height: innerHeight },
      navigation: performance.getEntriesByType("navigation")[0].encodedBodySize,
      resources: performance.getEntriesByType("resource").map((r) => ({ name: r.name, encoded: r.encodedBodySize })),
      images: [...document.images].map((image) => ({ src: image.currentSrc, width: image.naturalWidth, height: image.naturalHeight })),
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    }));
    Object.assign(report, { generatedAt: new Date().toISOString(), source, baseURL, failures });
    report.total = report.navigation + report.resources.reduce((sum, resource) => sum + resource.encoded, 0);
    fs.writeFileSync(`${evidence}/frontend-${source}-assets-${width}.json`, JSON.stringify(report, null, 2));
    if (failures.length || report.horizontalOverflow) throw new Error("Landing rendering failed");
    if (report.total > 600 * 1024) throw new Error("Landing asset budget exceeded");
    console.log(`${source} ${label}: ${report.total} bytes`);
    await page.close();
  }
} finally {
  await browser.close();
}
