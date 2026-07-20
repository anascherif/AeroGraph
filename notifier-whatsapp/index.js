// AeroGraph WhatsApp bridge (Baileys)
// -----------------------------------------------
// Tiny local HTTP service that lets the Python backend send WhatsApp
// messages (text + up to 3 JPEG photos) via the open-source Baileys
// library, without paying for the WhatsApp Business API.
//
// Contract:
//   POST /send
//     body: { phone: "<1234567890>", text: "...", images_base64: ["...", "..."] }
//     resp: { ok: true | false, detail: string }
//
//   GET  /health
//     resp: { ok: true, authenticated: bool, ready_to_send: bool }
//
// Auth:
//   First run: a QR code prints to the terminal. Scan it with the WhatsApp
//   app on your phone (Settings → Linked Devices → Link a Device). Auth
//   state is persisted in ./auth/ (gitignored).
//   Subsequent runs: no QR; uses persisted credentials.

import express from "express";
import pino from "pino";
import qrcode from "qrcode-terminal";
import makeWASocket, { useMultiFileAuthState, DisconnectReason } from "@whiskeysockets/baileys";

const logger = pino({ level: "info" });
const app = express();
app.use(express.json({ limit: "10mb" }));

let sock = null;
let ready = false;

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState("./auth");
  sock = makeWASocket({
    auth: state,
    logger,
    printQRInTerminal: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      console.log("\n[whatsapp] Scan this QR with your WhatsApp app:");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "open") {
      ready = true;
      console.log("[whatsapp] Connected and ready to send messages.");
    } else if (connection === "close") {
      ready = false;
      const shouldReconnect =
        lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      if (shouldReconnect) {
        console.log("[whatsapp] Connection closed, reconnecting...");
        startSock();
      } else {
        console.log("[whatsapp] Logged out — delete ./auth/ and restart to re-pair.");
      }
    }
  });
}

await startSock();

// --- /health ----------------------------------------------------------------
app.get("/health", (req, res) => {
  res.json({ ok: true, authenticated: ready, ready_to_send: ready });
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
    const jid = phone.endsWith("@s.whatsapp.net") ? phone : `${phone}@s.whatsapp.net`;

    // 1. Send text
    await sock.sendMessage(jid, { text });

    // 2. Send images (each as its own message — WhatsApp groups them visually)
    const imgs = Array.isArray(images_base64) ? images_base64.slice(0, 3) : [];
    for (let i = 0; i < imgs.length; i++) {
      const b64 = imgs[i];
      try {
        const buf = Buffer.from(b64, "base64");
        await sock.sendMessage(jid, {
          image: buf,
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
  console.log(`[whatsapp] Baileys bridge listening on http://127.0.0.1:${PORT}`);
  if (!ready) {
    console.log("[whatsapp] Waiting for QR scan / device link...");
  }
});
