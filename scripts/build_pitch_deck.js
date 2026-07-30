const PptxGenJS = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

// ── Palette (matches docs/header-banner.svg) ──────────────────────────
const C = {
  navy: "0A1628",
  navyMid: "1E3A5F",
  cyan: "22D3EE",
  white: "F1F5F9",
  slate: "94A3B8",
  darkBg: "0A1628",
  contentBg: "FFFFFF",
  accent: "22D3EE",
};

// ── Helper: centered icon circle ──────────────────────────────────────
function addRadarIcon(slide, x, y, r, fill) {
  slide.addShape("OVAL", { x: x - r, y: y - r, w: r * 2, h: r * 2, fill: { color: fill } });
  slide.addShape("OVAL", {
    x: x - r * 0.35, y: y - r * 0.35, w: r * 0.7, h: r * 0.7,
    fill: { color: "FFFFFF" },
  });
  slide.addShape("OVAL", {
    x: x - r * 0.12, y: y - r * 0.12, w: r * 0.24, h: r * 0.24,
    fill: { color: fill },
  });
}

// ── Helper: white-background content slide ────────────────────────────
function contentSlide(deck, title) {
  const slide = deck.addSlide();
  slide.background = { color: C.contentBg };
  // Header strip across the top
  slide.addShape("RECTANGLE", {
    x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.accent },
  });
  addRadarIcon(slide, 0.45, 0.55, 0.2, C.accent);
  slide.addText(title, {
    x: 0.85, y: 0.35, w: 8, h: 0.5, fontFace: "Cambria", fontSize: 28,
    bold: true, color: C.navy,
  });
  return slide;
}

// ── Helper: dark-background full-bleed slide ──────────────────────────
function darkSlide(deck) {
  const slide = deck.addSlide();
  slide.background = { color: C.darkBg };
  return slide;
}

// ── Build deck ────────────────────────────────────────────────────────
function build() {
  const deck = new PptxGenJS();
  deck.layout = "LAYOUT_WIDE"; // 13.3" x 7.5"

  // ────── Slide 1: Title (dark) ───────────────────────────────────────
  {
    const sl = darkSlide(deck);
    // Large radar icon as hero
    addRadarIcon(sl, 6.65, 2.2, 0.9, C.accent);
    sl.addText("AeroGraph", {
      x: 1, y: 3.4, w: 11.3, h: 1, fontFace: "Cambria", fontSize: 64,
      bold: true, color: C.white, align: "center", charSpacing: -1,
    });
    sl.addText("A spatial-temporal memory engine for visually impaired users", {
      x: 1.5, y: 4.4, w: 10.3, h: 0.7, fontFace: "Calibri", fontSize: 22,
      color: C.slate, align: "center",
    });
    sl.addText("Assistive Innovation Challenge 2026  ·  Devpost  ·  August 1, 2026", {
      x: 2, y: 5.8, w: 9.3, h: 0.4, fontFace: "Calibri", fontSize: 12,
      color: C.slate, align: "center",
    });
    // Bottom accent bar
    sl.addShape("RECTANGLE", {
      x: 3.5, y: 6.5, w: 6.3, h: 0.04, fill: { color: C.accent },
    });
  }

  // ────── Slide 2: Problem statement (light) ──────────────────────────
  {
    const sl = contentSlide(deck, "The problem");
    sl.addText([
      { text: "1 in 28", options: { fontSize: 48, bold: true, color: C.accent } },
      { text: " people worldwide live with significant visual impairment (WHO).\n\n", options: { fontSize: 18, color: C.navy, breakLine: true } },
      { text: "For a sighted person, walking into a room tells you everything: where the furniture is, what changed since yesterday, where you left your keys.\n\n", options: { fontSize: 16, color: "333333", breakLine: true } },
      { text: "For a blind or low-vision person, every visit is a fresh scan — there is no \"memory of space.\" Objects move. Hazards appear. The environment changes silently.", options: { fontSize: 16, color: "333333" } },
    ], {
      x: 0.85, y: 1.2, w: 7.5, h: 5,
      fontFace: "Calibri", valign: "top", lineSpacingMultiple: 1.3,
    });
    // Right side: icon + stat callout
    addRadarIcon(sl, 9.8, 1.8, 0.5, C.accent);
    sl.addText("253 million", {
      x: 8.5, y: 2.6, w: 4, h: 0.7, fontFace: "Cambria", fontSize: 36,
      bold: true, color: C.navy, align: "center",
    });
    sl.addText("people visually impaired globally\n(WHO, 2023)", {
      x: 8.5, y: 3.2, w: 4, h: 0.6, fontFace: "Calibri", fontSize: 12,
      color: C.slate, align: "center", lineSpacingMultiple: 1.3,
    });
  }

  // ────── Slide 3: Insight + architecture (light) ─────────────────────
  {
    const sl = contentSlide(deck, "How it works");
    sl.addText([
      { text: "A body-worn camera + on-device spatial graph + voice interface", options: { fontSize: 18, bold: true, color: C.navy, breakLine: true } },
      { text: "= a continuous photographic memory of the user's environment.", options: { fontSize: 18, bold: true, color: C.accent } },
    ], {
      x: 0.85, y: 1.0, w: 8.5, h: 1, fontFace: "Calibri",
    });

    // Pipeline cards
    const cards = [
      { title: "1. DETECT", body: "YOLO11n ONNX pipeline\ndetects 49 COCO classes\nat 5 FPS on CPU only", x: 0.5, w: 2.8 },
      { title: "2. GRAPH", body: "Spatial encoding into\nChromaDB vector store.\nObjects + locations + time.", x: 3.6, w: 2.8 },
      { title: "3. QUERY", body: "Voice RAG via NVIDIA NIM\n(Groq STT fallback).\n\"Where did I leave X?\"", x: 6.7, w: 2.8 },
      { title: "4. RESPOND", body: "SAPI5 TTS (English voice).\nOr sends alert to family\nif you don't respond.", x: 9.8, w: 2.8 },
    ];
    cards.forEach((c) => {
      sl.addShape("ROUNDED_RECTANGLE", {
        x: c.x, y: 2.5, w: c.w, h: 3.5,
        fill: { color: "F0F4F8" }, rectRadius: 0.2,
      });
      sl.addText(c.title, {
        x: c.x, y: 2.7, w: c.w, h: 0.5, fontFace: "Cambria",
        fontSize: 14, bold: true, color: C.accent, align: "center",
      });
      sl.addText(c.body, {
        x: c.x + 0.15, y: 3.3, w: c.w - 0.3, h: 2,
        fontFace: "Calibri", fontSize: 13, color: "333333", align: "center",
        lineSpacingMultiple: 1.4,
      });
    });
  }

  // ────── Slide 4: Tech stack (light, two-column) ─────────────────────
  {
    const sl = contentSlide(deck, "Tech stack — $0 budget, CPU-only");
    const leftItems = [
      ["Computer Vision", "YOLO11n (ONNX Runtime)\n49 classes, ~0.3s per frame"],
      ["Spatial Memory", "ChromaDB vector store\nLocation-aware embeddings"],
    ];
    const rightItems = [
      ["Backend", "FastAPI + asyncio\n3-tier notifier bus"],
      ["Frontend", "Next.js 16 + React 19\nTailwind v4, shadcn/ui"],
      ["Voice", "Whisper STT (Groq)\nSAPI5 TTS (English)"],
    ];
    const renderCol = (items, startX) => {
      items.forEach(([title, body], i) => {
        const y = 1.3 + i * 2.0;
        sl.addShape("ROUNDED_RECTANGLE", {
          x: startX, y: y, w: 5.2, h: 1.7,
          fill: { color: "F0F4F8" }, rectRadius: 0.15,
        });
        addRadarIcon(sl, startX + 0.35, y + 0.4, 0.18, C.accent);
        sl.addText(title, {
          x: startX + 0.7, y: y + 0.15, w: 4.2, h: 0.4,
          fontFace: "Cambria", fontSize: 16, bold: true, color: C.navy,
        });
        sl.addText(body, {
          x: startX + 0.7, y: y + 0.55, w: 4.2, h: 0.9,
          fontFace: "Calibri", fontSize: 13, color: "555555",
          lineSpacingMultiple: 1.3,
        });
      });
    };
    renderCol(leftItems, 0.5);
    renderCol(rightItems, 6.5);
    sl.addText("All models run locally. No GPU required. No cloud costs.", {
      x: 0.5, y: 6.0, w: 12.3, h: 0.5, fontFace: "Calibri", fontSize: 13,
      italic: true, color: C.slate, align: "center",
    });
  }

  // ────── Slide 5: Live detection demo (light) ────────────────────────
  {
    const sl = contentSlide(deck, "Demo: live detection");
    sl.addText([
      { text: "Camera feed, annotated in real time\n\n", options: { bold: true, fontSize: 16, color: C.navy, breakLine: true } },
      { text: "YOLO11n draws bounding boxes around detected objects:\n", options: { fontSize: 15, color: "333333", breakLine: true } },
      { text: "\"Door ahead, 2 metres. Desk to your left. Chair behind you.\"\n\n", options: { fontSize: 18, color: C.accent, breakLine: true, italic: true } },
      { text: "49 object classes  ·  5 FPS on CPU  ·  60+ sessions stored\n", options: { fontSize: 13, color: C.slate, breakLine: true } },
      { text: "Body-worn camera  ·  User never in frame  ·  TTS speaks positions aloud", options: { fontSize: 13, color: C.slate } },
    ], {
      x: 0.85, y: 1.2, w: 11.3, h: 5,
      fontFace: "Calibri", valign: "top", lineSpacingMultiple: 1.6,
    });
  }

  // ────── Slide 6: Temporal diff demo (light) ─────────────────────────
  {
    const sl = contentSlide(deck, "Demo: environment change detection");
    sl.addText([
      { text: "On a return visit: ", options: { fontSize: 18, color: C.navy } },
      { text: "\"Your keys moved 1.2 metres to the right of the desk.\"", options: { fontSize: 20, bold: true, color: C.accent } },
    ], {
      x: 0.85, y: 1.0, w: 11.5, h: 0.8, fontFace: "Calibri",
    });
    // Comparison mock-up
    const items = [
      { label: "Previous visit", items: ["Chair, desk, door, box", "Keys on desk (left side)", "No hazards detected"] },
      { label: "Now", items: ["Same objects + new hazard (bottle)", "Keys moved 1.2m right", "Alert: new obstacle at door"] },
    ];
    items.forEach((col, ci) => {
      const x = 0.5 + ci * 5.8;
      sl.addShape("ROUNDED_RECTANGLE", {
        x, y: 2.1, w: 5.3, h: 3.8,
        fill: { color: ci === 0 ? "F0F4F8" : "E3F5F7" }, rectRadius: 0.2,
      });
      const headerColor = ci === 0 ? C.navy : C.accent;
      sl.addText(col.label, {
        x, y: 2.3, w: 5.3, h: 0.5, fontFace: "Cambria", fontSize: 16,
        bold: true, color: headerColor, align: "center",
      });
      sl.addText(col.items.join("\n\n"), {
        x: x + 0.3, y: 2.9, w: 4.7, h: 2.8,
        fontFace: "Calibri", fontSize: 14, color: "333333",
        lineSpacingMultiple: 1.4,
      });
    });
  }

  // ────── Slide 7: Voice query demo (light) ──────────────────────────
  {
    const sl = contentSlide(deck, "Demo: natural-language voice query");
    sl.addText([
      { text: "User (voice):  ", options: { color: C.slate, italic: true } },
      { text: "\"Where did I leave the blue bottle?\"\n\n", options: { bold: true, fontSize: 20, color: C.navy } },
      { text: "AeroGraph (voice):  ", options: { color: C.slate, italic: true } },
      { text: "\"The blue bottle is on the table in the kitchen, 2 metres to your left.", options: { bold: true, fontSize: 20, color: C.accent } },
    ], {
      x: 0.85, y: 1.0, w: 11.5, h: 2, fontFace: "Calibri",
    });

    // Flow diagram boxes
    const steps = [
      { label: "Audio capture", desc: "Whisper STT\n(Groq free tier)", x: 0.5 },
      { label: "Embed + search", desc: "Spatial graph query\nin ChromaDB", x: 3.6 },
      { label: "LLM answer", desc: "NVIDIA NIM API\n(optional Groq)", x: 6.7 },
      { label: "TTS out", desc: "SAPI5 English\nvoice pin", x: 9.8 },
    ];
    steps.forEach((s) => {
      sl.addShape("ROUNDED_RECTANGLE", {
        x: s.x, y: 3.5, w: 2.8, h: 2.2,
        fill: { color: "F0F4F8" }, rectRadius: 0.15,
      });
      sl.addText(s.label, {
        x: s.x, y: 3.7, w: 2.8, h: 0.4, fontFace: "Cambria",
        fontSize: 14, bold: true, color: C.navy, align: "center",
      });
      sl.addText(s.desc, {
        x: s.x + 0.15, y: 4.2, w: 2.5, h: 1.2, fontFace: "Calibri",
        fontSize: 13, color: "555555", align: "center", lineSpacingMultiple: 1.3,
      });
      // Arrow between boxes
      if (s.x < 9.8) {
        sl.addText("\u2192", {
          x: s.x + 2.6, y: 4.0, w: 1, h: 0.6, fontFace: "Calibri",
          fontSize: 24, bold: true, color: C.accent, align: "center",
        });
      }
    });
  }

  // ────── Slide 8: Safety state machine (light) ───────────────────────
  {
    const sl = contentSlide(deck, "Safety monitor — body-cam distress detection");
    const states = [
      { name: "MONITORING", color: C.navy, desc: "3 signals watch:\nmotion, tilt, brightness" },
      { name: "CONFIRMING", color: "F59E0B", desc: "30s voice prompt:\n\"Say I'm okay\"" },
      { name: "ESCALATING", color: "EF4444", desc: "Contact family via\nTelegram + WhatsApp" },
      { name: "COOLDOWN", color: C.slate, desc: "60s pause\nbefore re-arming" },
    ];
    const lightBg = { navy: "E8EEF5", amber: "FEF3C7", red: "FEE2E2", slate: "F1F5F9" };
    const nameToBg = { MONITORING: "navy", CONFIRMING: "amber", ESCALATING: "red", COOLDOWN: "slate" };
    states.forEach((s, i) => {
      const x = 0.5 + i * 3.15;
      sl.addShape("ROUNDED_RECTANGLE", {
        x, y: 1.4, w: 2.8, h: 3.2,
        fill: { color: lightBg[nameToBg[s.name]] }, rectRadius: 0.15,
      });
      sl.addText(s.name, {
        x, y: 1.6, w: 2.8, h: 0.5, fontFace: "Consolas", fontSize: 11,
        bold: true, color: s.color, align: "center",
      });
      sl.addText(s.desc, {
        x: x + 0.15, y: 2.3, w: 2.5, h: 2,
        fontFace: "Calibri", fontSize: 13, color: "333333", align: "center",
        lineSpacingMultiple: 1.3,
      });
      // Arrow
      if (i < 3) {
        sl.addText("\u2192", {
          x: x + 2.5, y: 2.5, w: 0.9, h: 0.6, fontFace: "Calibri",
          fontSize: 24, bold: true, color: C.slate, align: "center",
        });
      }
    });
    sl.addText("3 orthogonal signals fused with debounce. \"Was-moving-within-60s\" guard prevents false alarms.", {
      x: 0.5, y: 5.0, w: 12.3, h: 0.5, fontFace: "Calibri", fontSize: 13,
      italic: true, color: C.slate, align: "center",
    });
  }

  // ────── Slide 9: Multi-channel escalation (light) ──────────────────
  {
    const sl = contentSlide(deck, "Multi-channel alerting — 3 tiers");
    const channels = [
      { name: "Telegram", tier: "Primary", icon: "\u2709", desc: "Free, worldwide.\nBot sends text + voice note.\nConfigured: YES", ok: true },
      { name: "WhatsApp", tier: "Secondary", icon: "\uD83D\uDCF1", desc: "Free, works in Tunisia.\nLocal Node bridge.\nConfigured: needs QR", ok: "partial" },
      { name: "Twilio", tier: "Tertiary", icon: "\uD83D\uDCDE", desc: "Paid voice calls.\nEnv-guarded, dry-run by default.\nConfigured: NO", ok: false },
    ];
    const perRow = 3;
    const colW = 3.5;
    const startX = (13.3 - perRow * colW) / 2;
    channels.forEach((ch, i) => {
      const x = startX + i * (colW + 0.5);
      const y = 1.6;
      sl.addShape("ROUNDED_RECTANGLE", {
        x, y, w: colW, h: 4.2, fill: { color: "F0F4F8" }, rectRadius: 0.2,
      });
      addRadarIcon(sl, x + colW / 2, y + 0.8, 0.3, ch.ok === true ? C.accent : ch.ok === "partial" ? "F59E0B" : "EF4444");
      sl.addText(ch.tier, {
        x, y: 1.4, w: colW, h: 0.4, fontFace: "Consolas", fontSize: 10,
        bold: true, color: C.slate, align: "center",
      });
      sl.addText(ch.name, {
        x, y: 1.8, w: colW, h: 0.5, fontFace: "Cambria", fontSize: 18,
        bold: true, color: C.navy, align: "center",
      });
      sl.addText(ch.desc, {
        x: x + 0.2, y: 2.6, w: colW - 0.4, h: 2.5,
        fontFace: "Calibri", fontSize: 13, color: "444444", align: "center",
        lineSpacingMultiple: 1.4,
      });
    });
  }

  // ────── Slide 10: 30-second safety flow (light) ────────────────────
  {
    const sl = contentSlide(deck, "The 30-second safety flow (verified)");
    // Timeline
    const steps = [
      { t: "0s", label: "Alert triggered", desc: "3/3 signals\nfused", color: C.navy },
      { t: "+2s", label: "Voice prompt", desc: "TTS: \"Are you\nokay?\"", color: "F59E0B" },
      { t: "+30s", label: "No response", desc: "State machine\nescalates", color: "EF4444" },
      { t: "+31s", label: "Telegram sent", desc: "Text + voice note\ndelivered", color: C.accent },
      { t: "+32s", label: "WhatsApp sent", desc: "When bridge\nconnected", color: C.accent },
    ];
    // Timeline line
    sl.addShape("RECTANGLE", {
      x: 0.5, y: 2.0, w: 12.3, h: 0.04, fill: { color: C.accent },
    });
    steps.forEach((s, i) => {
      const x = 0.5 + i * 2.5;
      sl.addShape("OVAL", {
        x: x + 0.8, y: 1.72, w: 0.35, h: 0.35,
        fill: { color: s.color },
      });
      sl.addText(s.t, {
        x: x + 0.2, y: 2.2, w: 1.5, h: 0.4, fontFace: "Consolas",
        fontSize: 11, bold: true, color: C.navy, align: "center",
      });
      sl.addText(s.label, {
        x: x + 0.2, y: 2.6, w: 1.5, h: 0.4, fontFace: "Cambria",
        fontSize: 14, bold: true, color: C.navy, align: "center",
      });
      sl.addText(s.desc, {
        x: x + 0.2, y: 3.1, w: 1.5, h: 1, fontFace: "Calibri",
        fontSize: 11, color: "555555", align: "center", lineSpacingMultiple: 1.3,
      });
    });
    // Incident card at bottom
    sl.addShape("ROUNDED_RECTANGLE", {
      x: 2, y: 4.5, w: 9.3, h: 1.8, fill: { color: "E3F5F7" }, rectRadius: 0.15,
    });
    sl.addText([
      { text: "Real incident from test run:   ", options: { bold: true, color: C.navy } },
      { text: "inc_ebfb4714528b", options: { color: C.accent, fontFace: "Consolas", fontSize: 12 } },
      { text: "\nTelegram -> 200 OK (text + voice note)        ", options: { color: "333333", breakLine: true } },
      { text: "WhatsApp -> bridge offline (re-link after 24h)        ", options: { color: "333333", breakLine: true } },
      { text: "State: monitored -> confirmed (30s) -> escalated -> cooldown", options: { color: C.slate, italic: true, fontSize: 12 } },
    ], {
      x: 2.3, y: 4.7, w: 8.7, h: 1.5, fontFace: "Calibri", fontSize: 13,
      lineSpacingMultiple: 1.4,
    });
  }

  // ────── Slide 11: Why it matters (dark) ─────────────────────────────
  {
    const sl = darkSlide(deck);
    addRadarIcon(sl, 6.65, 2.0, 0.6, C.accent);
    sl.addText("Why this matters", {
      x: 1, y: 3.0, w: 11.3, h: 0.8, fontFace: "Cambria", fontSize: 44,
      bold: true, color: C.white, align: "center",
    });
    const points = [
      "\u2713  $0 budget, CPU-only",
      "\u2713  Low ban-risk WhatsApp bridge (real headless Chromium)",
      "\u2713  Full 29-pass regression test suite",
      "\u2713  Accessible dashboard + voice-first UX",
    ];
    sl.addText(points.map((p) => ({ text: p, options: { breakLine: true, fontSize: 18, color: C.white, margin: 0, spaceBefore: 6, spaceAfter: 6, paraSpaceAfter: 12, bullet: true } })), {
      x: 2, y: 4.0, w: 9.3, h: 3,
      fontFace: "Calibri", valign: "top",
    });
    sl.addShape("RECTANGLE", {
      x: 3.5, y: 6.8, w: 6.3, h: 0.04, fill: { color: C.accent },
    });
  }

  // ────── Slide 12: Closing / Thank you (dark) ───────────────────────
  {
    const sl = darkSlide(deck);
    addRadarIcon(sl, 6.65, 2.1, 0.5, C.accent);
    sl.addText("Thank you", {
      x: 1, y: 3.2, w: 11.3, h: 0.8, fontFace: "Cambria", fontSize: 52,
      bold: true, color: C.white, align: "center",
    });
    sl.addText("Built for the Assistive Innovation Challenge 2026", {
      x: 1, y: 4.1, w: 11.3, h: 0.5, fontFace: "Calibri", fontSize: 18,
      color: C.slate, align: "center",
    });
    sl.addText([
      { text: "Telegram: @AnasAeroGraphbot  |  ", options: { color: C.slate, fontSize: 12 } },
      { text: "GitHub: github.com/anomalyco/AeroGraph", options: { color: C.accent, fontSize: 12 } },
    ], {
      x: 1, y: 5.5, w: 11.3, h: 0.4, fontFace: "Calibri",
      align: "center",
    });
    sl.addShape("RECTANGLE", {
      x: 4.5, y: 6.5, w: 4.3, h: 0.04, fill: { color: C.accent },
    });
  }

  // ── Write file ──────────────────────────────────────────────────────
  const outPath = path.join(__dirname, "..", "docs", "pitch-deck.pptx");
  deck.writeFile({ fileName: outPath }).then(() => {
    console.log("Written:", outPath, `(${(fs.statSync(outPath).size / 1024).toFixed(0)} KB)`);
  }).catch((err) => {
    console.error("Failed:", err);
    process.exit(1);
  });
}

build();
