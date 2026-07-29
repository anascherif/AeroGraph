// AeroGraph WhatsApp bridge (whatsapp-web.js)
// -----------------------------------------------
// Tiny local HTTP service that lets the Python backend send WhatsApp
// messages (text + up to 3 JPEG photos) via the whatsapp-web.js library,
// which drives a real headless Chromium — looks like genuine WhatsApp Web
// traffic, much lower ban-risk than Baileys.
//
// Contract:
//   POST /send
//     body: { phone: "<1234567890>", text: "...", images_base64: ["...", "..."] }
//     resp: { ok: true | false, detail: string }
//
//   GET  /health
//     resp: { ok: true, authenticated: bool, ready_to_send: bool }
//
//   GET  /qr
//     resp: { qr: "<data-uri>" }  OR  { qr: null, authenticated: true }
//
// Auth:
//   First run: GET /qr returns a data URI; render it in a browser/QR scanner
//   and scan with the WhatsApp app on your phone (Settings → Linked Devices
//   → Link a Device). Auth state is persisted in ./auth/ (gitignored).
//   Subsequent runs: no QR; uses persisted credentials.

import express from "express";
import pkg from "whatsapp-web.js";
const { Client, LocalAuth, MessageMedia } = pkg;
import QRCode from "qrcode";
import { existsSync, writeFileSync, unlinkSync } from "node:fs";

const app = express();
app.use(express.json({ limit: "10mb" }));

let qrDataUri = null;
let qrPngPath = "./qr.png";
let ready = false;

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

client.on("qr", async (qr) => {
  try {
    qrDataUri = await QRCode.toDataURL(qr, { width: 480, margin: 2 });
    const pngBuf = await QRCode.toFile(qrPngPath, qr, { width: 480, margin: 2 });
    console.log(`[whatsapp] QR saved to ${qrPngPath} — open it and scan with WhatsApp.`);
    console.log("[whatsapp] Or GET http://127.0.0.1:7878/qr for a data URI.");
  } catch (e) {
    console.error("[whatsapp] Failed to render QR:", e.message);
  }
});

client.on("ready", () => {
  ready = true;
  qrDataUri = null;
  if (existsSync(qrPngPath)) {
    try { unlinkSync(qrPngPath); } catch {}
  }
  console.log("[whatsapp] Connected and ready to send messages.");
});

client.on("authenticated", () => {
  console.log("[whatsapp] Authenticated — session saved.");
});

client.on("auth_failure", (msg) => {
  console.error("[whatsapp] Auth failure:", msg);
});

client.on("disconnected", (reason) => {
  ready = false;
  console.warn("[whatsapp] Disconnected:", reason);
  // whatsapp-web.js will attempt to reconnect automatically.
});

client.initialize().catch((e) => {
  console.error("[whatsapp] initialize() failed:", e);
});

// --- /health ----------------------------------------------------------------
app.get("/health", (req, res) => {
  res.json({ ok: true, authenticated: ready, ready_to_send: ready });
});

// --- /qr --------------------------------------------------------------------
// Returns the current QR as a data URI (for browser rendering), or null when
// already authenticated. Useful for the frontend dashboard.
app.get("/qr", (req, res) => {
  res.json({ qr: ready ? null : qrDataUri, authenticated: ready });
});

// --- /send ------------------------------------------------------------------
// phone: full international number, NO plus sign, NO spaces (e.g. "21612345678")
// text: alert body text
// images_base64: array of base64-encoded JPEG strings (max 3 sent)
app.post("/send", async (req, res) => {
  try {
    const { phone, text, images_base64 } = req.body || {};
    if (!phone || !text) {
      return res
        .status(400)
        .json({ ok: false, detail: "missing 'phone' or 'text'" });
    }
    if (!ready) {
      return res
        .status(503)
        .json({ ok: false, detail: "whatsapp not authenticated yet (scan QR)" });
    }

    // whatsapp-web.js expects chatId in the form <digits>@c.us. Strip any
    // '+', spaces, dashes, or parentheses so callers can pass either format.
    const cleanPhone = String(phone).replace(/[^0-9]/g, "");
    const chatId = cleanPhone.endsWith("@c.us") ? cleanPhone : `${cleanPhone}@c.us`;

    // 1. Send text
    await client.sendMessage(chatId, text);

    // 2. Send images (each as its own message — WhatsApp groups them visually)
    const imgs = Array.isArray(images_base64) ? images_base64.slice(0, 3) : [];
    for (let i = 0; i < imgs.length; i++) {
      const b64 = imgs[i];
      try {
        // Strip any data-uri prefix ("data:image/jpeg;base64,")
        const raw = b64.includes(",") ? b64.split(",")[1] : b64;
        const media = new MessageMedia("image/jpeg", raw, `frame${i}.jpg`);
        await client.sendMessage(chatId, media, {
          caption: i === 0 ? "AeroGraph: recent camera frames" : undefined,
        });
      } catch (e) {
        console.warn(`[whatsapp] image ${i} failed:`, e.message);
      }
    }

    return res.json({
      ok: true,
      detail: `sent to ${phone} (text + ${imgs.length} image(s))`,
    });
  } catch (e) {
    console.error("[whatsapp] /send error:", e);
    return res.status(500).json({ ok: false, detail: String(e?.message || e) });
  }
});

const PORT = Number(process.env.WA_BRIDGE_PORT || 7878);
app.listen(PORT, "127.0.0.1", () => {
  console.log(`[whatsapp] whatsapp-web.js bridge listening on http://127.0.0.1:${PORT}`);
  if (!ready) {
    console.log("[whatsapp] Waiting for QR scan / device link...");
    console.log("[whatsapp] Open qr.png (or GET /qr) and scan with WhatsApp.");
  }
});
