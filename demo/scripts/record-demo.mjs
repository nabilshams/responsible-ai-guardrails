import { chromium } from "playwright";
import { readFile, mkdir, mkdtemp, rm, writeFile, stat, copyFile } from "node:fs/promises";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { performance } from "node:perf_hooks";

const here = dirname(fileURLToPath(import.meta.url));
const demoRoot = resolve(here, "..");
const repositoryRoot = resolve(demoRoot, "..");
const outputRoot = join(demoRoot, "output");
const screenshotsRoot = join(outputRoot, "screenshots");
const manifestPath = join(outputRoot, "speech-manifest.json");
const sequencePath = join(outputRoot, "recording-sequence.json");
const narrationScriptPath = join(demoRoot, "narration", "script.txt");
const allowedFixtures = new Set([
  "synthetic-contact.txt",
  "synthetic-secrets.txt",
  "synthetic-pii-form.pdf",
  "synthetic-pii-record.docx",
  "synthetic-pii-image.png",
]);
const sceneIds = [
  "introduction",
  "purpose",
  "text",
  "document",
  "image",
  "ecosystem",
  "closing",
];
const callouts = [
  "Personal information and credentials can enter an AI workflow unintentionally.",
  "Create a redacted copy for review before use or sharing.",
  "Text protection for personal information and runtime credentials",
  "Documents: review a redacted PDF or Word copy before use.",
  "Images: OCR locates text; detected personal information is masked.",
  "Complements Microsoft services; it does not replace them.",
  "Always review the redacted copy. Detection is not guaranteed.\nProtect sensitive information before it enters your enterprise AI workflow.",
];
const capturePrivacyText = "Synthetic sample loaded for processing; source text is hidden in this recording.";
const expectedSceneCount = sceneIds.length;

function ensureInsideOutput(filePath) {
  const target = resolve(filePath);
  if (!target.startsWith(`${resolve(outputRoot)}${sep}`)) {
    throw new Error("Generated asset path is outside demo/output.");
  }
  return target;
}

function validateAppUrl(value) {
  try {
    const url = new URL(value);
    const localHost = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (
      !["https:", "http:"].includes(url.protocol)
      || (url.protocol === "http:" && !localHost)
      || url.username
      || url.password
      || url.search
      || url.hash
      || !["", "/"].includes(url.pathname)
    ) {
      throw new Error();
    }
    return url.origin;
  } catch {
    throw new Error("The application URL is invalid; use an HTTPS application base URL.");
  }
}

async function fixturePath(filename) {
  if (!allowedFixtures.has(filename)) {
    throw new Error("A required sample is not on the synthetic fixture allow-list.");
  }
  const inputRoot = resolve(repositoryRoot, "samples", "input");
  const path = resolve(inputRoot, filename);
  if (!path.startsWith(`${inputRoot}${sep}`)) {
    throw new Error("A required sample is outside samples/input.");
  }
  await stat(path);
  return path;
}

async function loadManifest() {
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const narrationScript = await readFile(narrationScriptPath);
  const scriptHash = createHash("sha256").update(narrationScript).digest("hex");
  if (
    manifest.script_sha256 !== scriptHash
    || !Array.isArray(manifest.scenes)
    || manifest.scenes.length !== expectedSceneCount
  ) {
    throw new Error("A complete local speech manifest is required; generate narration first.");
  }
  for (let index = 0; index < expectedSceneCount; index += 1) {
    const scene = manifest.scenes[index];
    if (
      scene.scene_id !== sceneIds[index]
      || scene.audio_file !== `speech-${String(index + 1).padStart(2, "0")}.wav`
      || !Number.isInteger(scene.duration_ms)
      || scene.duration_ms <= 0
    ) {
      throw new Error("The local speech manifest is invalid.");
    }
    await stat(ensureInsideOutput(join(outputRoot, scene.audio_file)));
  }
  return manifest;
}

function overlayStyle() {
  return `
    #demo-callout {
      position: fixed; z-index: 9999; top: 78px; left: 50%;
      width: min(1080px, calc(100vw - 520px)); padding: 22px 28px;
      border: 1px solid rgba(255,255,255,.62); border-radius: 12px;
      background: rgba(24, 32, 48, .96); color: #fff;
      font: 650 30px/1.32 "Segoe UI", Arial, sans-serif; letter-spacing: .1px;
      box-shadow: 0 8px 32px rgba(0,0,0,.28); white-space: pre-line; text-align: center;
      opacity: 0; transform: translate(-50%, -8px); transition: opacity .35s ease, transform .35s ease;
      pointer-events: none;
    }
    #demo-callout.visible { opacity: 1; transform: translate(-50%, 0); }
    #demo-input-cover {
      position: fixed; z-index: 9998; display: grid; place-items: center;
      border: 1px solid #919191; border-radius: 8px; background: #fff;
      color: #242424; font: 600 17px/1.4 "Segoe UI", Arial, sans-serif;
      text-align: center; padding: 12px; pointer-events: none;
    }
  `;
}

async function callout(page, text, durationMs) {
  await page.evaluate((content) => {
    let element = document.querySelector("#demo-callout");
    if (!element) {
      element = document.createElement("div");
      element.id = "demo-callout";
      element.setAttribute("aria-live", "polite");
      document.body.append(element);
    }
    element.textContent = content;
    element.classList.remove("visible");
    requestAnimationFrame(() => element.classList.add("visible"));
  }, text);

  const startMs = Math.max(0, Math.round(performance.now() - globalThis.demoRecordingStart));
  await page.waitForTimeout(durationMs);
  return { start_ms: startMs, duration_ms: durationMs };
}

async function hideCallout(page) {
  await page.evaluate(() => document.querySelector("#demo-callout")?.classList.remove("visible"));
  await page.waitForTimeout(400);
}

async function protectTextEntry(page) {
  await page.evaluate((label) => {
    const field = document.querySelector("#message");
    if (!(field instanceof HTMLElement)) throw new Error("Text entry is unavailable.");
    const rect = field.getBoundingClientRect();
    const cover = document.createElement("div");
    cover.id = "demo-input-cover";
    cover.textContent = label;
    cover.style.left = `${rect.left}px`;
    cover.style.top = `${rect.top}px`;
    cover.style.width = `${rect.width}px`;
    cover.style.height = `${rect.height}px`;
    document.body.append(cover);
  }, capturePrivacyText);
}

async function removeTextProtection(page) {
  await page.evaluate(() => document.querySelector("#demo-input-cover")?.remove());
}

async function assertNoSensitiveValues(text, sourceText) {
  const patterns = [
    /\b(?:my\s+name\s+is|full\s+name|name|contact|employee|customer|dear|i\s+am)\s*[:=,]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi,
    /\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/g,
    /\b(?:\+?\d[\d().\s-]{6,}\d)\b/g,
    /\b(?:password|secret|token|credential|api[_ -]?key|access[_ -]?key|connection[_ -]?string)\s*[:=]\s*[^\s,;]+/gi,
  ];
  const candidates = patterns.flatMap((pattern) =>
    [...sourceText.matchAll(pattern)].map((match) => match[1] ?? match[0]));
  if (candidates.some((value) => value.length >= 5 && text.toLocaleLowerCase().includes(value.toLocaleLowerCase()))) {
    throw new Error("The redacted text did not pass the demo privacy check.");
  }
}

async function clickSubmit(page) {
  await page.getByRole("button", { name: "Remove sensitive information" }).click();
}

async function waitForTextResult(page, sourceText) {
  const response = page.getByRole("article").filter({ hasText: "Redacted copy" }).last();
  await response.waitFor({ state: "visible", timeout: 120_000 });
  const meta = await response.innerText();
  if (!/items? detected and removed/i.test(meta) || !/review before use or sharing/i.test(meta)) {
    throw new Error("The text result did not include the expected count and review reminder.");
  }
  await assertNoSensitiveValues(meta, sourceText);
}

async function waitForFileResult(page) {
  const response = page.getByRole("article").filter({ hasText: "Redacted copy" }).last();
  const download = response.getByRole("button", { name: "Download" });
  await download.waitFor({ state: "visible", timeout: 180_000 });
  const detail = await response.innerText();
  const count = detail.match(/(\d+) items? detected and removed/i);
  if (!count || Number(count[1]) <= 0) {
    throw new Error("A reviewable redacted file and positive detection count were not returned.");
  }
}

async function clearConversation(page) {
  await page.getByRole("button", { name: "Clear conversation" }).click();
  await page.locator("#empty").waitFor({ state: "visible" });
}

async function saveScreenshot(page, name) {
  const target = ensureInsideOutput(join(screenshotsRoot, `${name}.png`));
  await page.screenshot({ path: target, animations: "disabled" });
}

async function main() {
  const appUrl = validateAppUrl(process.env.DEMO_APP_URL ?? "");
  const manifest = await loadManifest();
  await mkdir(screenshotsRoot, { recursive: true });
  const tempDirectory = await mkdtemp(join(outputRoot, ".recording-"));
  const events = [];
  let stage = "application startup";
  let browser;
  let context;
  let savedVideo;
  let startedAt = 0;

  try {
    browser = await chromium.launch({
      headless: true,
      args: [
        "--disable-notifications",
        "--disable-save-password-bubble",
        "--disable-password-manager-reauthentication",
        "--disable-features=PasswordManagerOnboarding,AutofillServerCommunication",
      ],
    });
    context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      deviceScaleFactor: 1,
      colorScheme: "light",
      locale: "en-AU",
      timezoneId: "Australia/Sydney",
      reducedMotion: "reduce",
      acceptDownloads: true,
      recordVideo: { dir: tempDirectory, size: { width: 1920, height: 1080 } },
    });
    const page = await context.newPage();
    startedAt = performance.now();
    globalThis.demoRecordingStart = startedAt;
    page.setDefaultTimeout(60_000);
    page.on("dialog", (dialog) => dialog.dismiss());
    const response = await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 45_000 });
    if (!response?.ok() || new URL(page.url()).origin !== new URL(appUrl).origin) {
      throw new Error("The application did not load directly.");
    }
    await page.addStyleTag({ content: overlayStyle() });
    await page.locator("#status").getByText("Service ready").waitFor({ state: "visible", timeout: 30_000 });
    await page.locator("#samples .sample-chip").first().waitFor({ state: "visible", timeout: 30_000 });

    stage = "introduction";
    await saveScreenshot(page, "01-landing");
    events.push({ scene_id: sceneIds[0], ...(await callout(page, callouts[0], manifest.scenes[0].duration_ms)) });
    await hideCallout(page);
    await page.waitForTimeout(15_000);

    stage = "product purpose";
    events.push({ scene_id: sceneIds[1], ...(await callout(page, callouts[1], manifest.scenes[1].duration_ms)) });
    await saveScreenshot(page, "02-capabilities");
    await hideCallout(page);
    await page.waitForTimeout(12_000);

    stage = "text redaction";
    const textFixture = await fixturePath("synthetic-contact.txt");
    const secretsFixture = await fixturePath("synthetic-secrets.txt");
    const sampleText = `${await readFile(textFixture, "utf8")}\n${await readFile(secretsFixture, "utf8")}`;
    await protectTextEntry(page);
    await page.locator("#message").fill(sampleText);
    await clickSubmit(page);
    await waitForTextResult(page, sampleText);
    await removeTextProtection(page);
    await saveScreenshot(page, "03-redacted-text");
    events.push({ scene_id: sceneIds[2], ...(await callout(page, callouts[2], manifest.scenes[2].duration_ms)) });
    await hideCallout(page);
    await page.waitForTimeout(12_000);

    stage = "document redaction";
    await clearConversation(page);
    await page.locator("#file-input").setInputFiles(await fixturePath("synthetic-pii-form.pdf"));
    await page.getByText("1 file selected", { exact: true }).waitFor({ state: "visible" });
    await clickSubmit(page);
    await waitForFileResult(page);
    await saveScreenshot(page, "04-redacted-document");
    events.push({ scene_id: sceneIds[3], ...(await callout(page, callouts[3], manifest.scenes[3].duration_ms)) });
    await hideCallout(page);
    await page.waitForTimeout(12_000);

    stage = "image redaction";
    await clearConversation(page);
    await page.locator("#file-input").setInputFiles(await fixturePath("synthetic-pii-image.png"));
    await page.getByText("1 file selected", { exact: true }).waitFor({ state: "visible" });
    await clickSubmit(page);
    await waitForFileResult(page);
    await saveScreenshot(page, "05-redacted-image");
    events.push({ scene_id: sceneIds[4], ...(await callout(page, callouts[4], manifest.scenes[4].duration_ms)) });
    await hideCallout(page);
    await page.waitForTimeout(12_000);

    stage = "Microsoft ecosystem positioning";
    await clearConversation(page);
    events.push({ scene_id: sceneIds[5], ...(await callout(page, callouts[5], manifest.scenes[5].duration_ms)) });
    await saveScreenshot(page, "06-ecosystem");
    await hideCallout(page);
    await page.waitForTimeout(12_000);

    stage = "responsible-use closing";
    events.push({ scene_id: sceneIds[6], ...(await callout(page, callouts[6], manifest.scenes[6].duration_ms)) });
    await saveScreenshot(page, "07-responsible-use");
    const minimumEndMs = 195_000;
    const remainingMs = Math.ceil(minimumEndMs - (performance.now() - startedAt));
    if (remainingMs > 0) await page.waitForTimeout(remainingMs);
    const totalDurationMs = Math.ceil(performance.now() - startedAt);
    if (totalDurationMs > 240_000) {
      throw new Error("The browser sequence exceeded the four-minute demo limit.");
    }
    if (
      events.length !== expectedSceneCount
      || events.some((event, index) => event.scene_id !== sceneIds[index])
    ) {
      throw new Error("The recorded scene order is invalid.");
    }
    savedVideo = await page.video().path();
    const videoTarget = ensureInsideOutput(join(outputRoot, "sensitive-data-protection-demo.webm"));
    await context.close();
    context = undefined;
    await copyFile(savedVideo, videoTarget);
    await writeFile(
      ensureInsideOutput(sequencePath),
      `${JSON.stringify({ total_duration_ms: totalDurationMs, scenes: events }, null, 2)}\n`,
      "utf8",
    );
  } catch {
    throw new Error(`Demo recording failed during ${stage}; no submitted content or diagnostic details were logged.`);
  } finally {
    if (context) await context.close().catch(() => undefined);
    if (browser) await browser.close().catch(() => undefined);
    await rm(tempDirectory, { recursive: true, force: true }).catch(() => undefined);
  }
}

main().then(
  () => console.log("Browser recording and reusable screenshots are ready; submitted content was not logged."),
  (error) => {
    console.error(error instanceof Error ? error.message : "Demo recording failed; no submitted content was logged.");
    process.exitCode = 1;
  },
);
