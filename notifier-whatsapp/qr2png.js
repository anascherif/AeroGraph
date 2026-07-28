// One-shot QR generator — opens Baileys, captures the first QR it sees,
// saves it as a PNG, and exits.
import makeWASocket, { useMultiFileAuthState, DisconnectReason } from "@whiskeysockets/baileys";
import QRCode from "qrcode";
import { writeFile } from "node:fs/promises";
import { existsSync, unlinkSync } from "node:fs";

const PNG_PATH = "./qr.png";
const TIMEOUT_MS = 60000;

if (existsSync(PNG_PATH)) unlinkSync(PNG_PATH);

const { state, saveCreds } = await useMultiFileAuthState("./auth");
const sock = makeWASocket({ auth: state, printQRInTerminal: false });

let qrSeen = false;

const timer = setTimeout(() => {
  if (!qrSeen) {
    console.error("[qr2png] Timed out waiting for QR");
    process.exit(1);
  }
}, TIMEOUT_MS);

sock.ev.on("creds.update", saveCreds);

sock.ev.on("connection.update", async (update) => {
  const { connection, lastDisconnect, qr } = update;
  if (qr && !qrSeen) {
    qrSeen = true;
    try {
      await QRCode.toFile(PNG_PATH, qr, { width: 600, margin: 2 });
      console.log(`[qr2png] QR saved to ${PNG_PATH}`);
      console.log(`[qr2png] Open this PNG on screen and scan with WhatsApp.`);
    } catch (e) {
      console.error("[qr2png] Failed to save PNG:", e);
      process.exit(1);
    }
  }
  if (connection === "open") {
    console.log("[qr2png] Authenticated! You can now close this script.");
    clearTimeout(timer);
    // Keep the process alive so the auth state persists.
    // The main bridge can be started later by running `node index.js`.
  } else if (connection === "close") {
    if (lastDisconnect?.error?.output?.statusCode === DisconnectReason.loggedOut) {
      console.error("[qr2png] Logged out — delete ./auth/ and restart");
      process.exit(1);
    }
  }
});
