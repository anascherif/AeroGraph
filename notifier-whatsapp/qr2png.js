// One-shot QR generator — opens whatsapp-web.js, captures the first QR it
// sees, saves it as a PNG, and waits for the user to scan it. Once scanned,
// the auth state is persisted in ./auth/ and the main bridge (index.js) can
// be started without needing another QR.
import pkg from "whatsapp-web.js";
const { Client, LocalAuth } = pkg;
import QRCode from "qrcode";
import { existsSync, unlinkSync } from "node:fs";

const PNG_PATH = "./qr.png";
const TIMEOUT_MS = 120000;

if (existsSync(PNG_PATH)) unlinkSync(PNG_PATH);

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: "./auth" }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  },
});

let qrSeen = false;

const timer = setTimeout(() => {
  if (!qrSeen) {
    console.error("[qr2png] Timed out waiting for QR");
    process.exit(1);
  }
}, TIMEOUT_MS);

client.on("qr", async (qr) => {
  qrSeen = true;
  try {
    await QRCode.toFile(PNG_PATH, qr, { width: 600, margin: 2 });
    console.log(`[qr2png] QR saved to ${PNG_PATH}`);
    console.log(`[qr2png] Open this PNG on screen and scan with WhatsApp.`);
    console.log(`[qr2png] (Settings -> Linked Devices -> Link a Device)`);
  } catch (e) {
    console.error("[qr2png] Failed to save PNG:", e);
    process.exit(1);
  }
});

client.on("authenticated", () => {
  console.log("[qr2png] Authenticated! Session saved.");
  clearTimeout(timer);
  // Wait ~2s for state to flush, then exit. The main bridge can be started
  // later by running `node index.js` and will use the persisted session.
  setTimeout(() => process.exit(0), 2000);
});

client.on("ready", () => {
  console.log("[qr2png] Client ready. Exiting.");
  clearTimeout(timer);
  process.exit(0);
});

client.initialize().catch((e) => {
  console.error("[qr2png] initialize() failed:", e);
  process.exit(1);
});
