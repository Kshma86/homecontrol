import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../..");
const defaultOutputRoot = path.join(repoRoot, "visual-audit", "runs");
const uiV2StorageKey = "hc-ui-v2-tabs";

function slug(value) {
  return String(value || "unknown")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "unknown";
}

function timestampParts(now = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  const day = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
  return { day, time };
}

function parseCliPayload() {
  const raw = process.argv[2];
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch (err) {
    throw new Error(`Invalid JSON payload: ${err.message}`);
  }
}

export async function captureVisualAudit(input = {}) {
  const tab = slug(input.tab || "home");
  const width = Number(input.width || 1440);
  const height = Number(input.height || 900);
  const safeWidth = Number.isFinite(width) && width > 0 ? Math.round(width) : 1440;
  const safeHeight = Number.isFinite(height) && height > 0 ? Math.round(height) : 900;
  const baseUrl = input.url || process.env.HC_VISUAL_AUDIT_URL || `http://127.0.0.1:3000/#${tab}`;
  const uiV2Tabs = input.uiV2Tabs && typeof input.uiV2Tabs === "object" ? input.uiV2Tabs : { [tab]: true };
  const outputRoot = path.resolve(process.env.HC_VISUAL_AUDIT_OUTPUT || defaultOutputRoot);
  const { day, time } = timestampParts();
  const dir = path.join(outputRoot, day, tab);
  const filename = `${time}-${safeWidth}x${safeHeight}.png`;
  const outputPath = path.join(dir, filename);

  await mkdir(dir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: safeWidth, height: safeHeight }, deviceScaleFactor: 1 });
    await page.addInitScript(({ key, value }) => {
      window.localStorage.setItem(key, JSON.stringify(value));
    }, { key: uiV2StorageKey, value: uiV2Tabs });
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 45000 });
    await page.waitForTimeout(Number(input.settleMs || 1200));
    await page.screenshot({ path: outputPath, fullPage: true });
  } finally {
    await browser.close();
  }

  return {
    ok: true,
    path: outputPath,
    relative_path: path.relative(repoRoot, outputPath),
    tab,
    width: safeWidth,
    height: safeHeight,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  captureVisualAudit(parseCliPayload())
    .then((result) => {
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    })
    .catch((err) => {
      process.stderr.write(`${err.stack || err.message}\n`);
      process.exit(1);
    });
}
