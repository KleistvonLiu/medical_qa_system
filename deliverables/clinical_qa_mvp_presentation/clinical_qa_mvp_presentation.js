"use strict";

const fs = require("fs");
const path = require("path");

const PptxGenJS = require("pptxgenjs");

const { autoFontSize, calcTextBox } = require("./pptxgenjs_helpers/text");
const { imageSizingContain } = require("./pptxgenjs_helpers/image");
const { svgToDataUri } = require("./pptxgenjs_helpers/svg");
const { safeOuterShadow } = require("./pptxgenjs_helpers/util");
const {
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require("./pptxgenjs_helpers/layout");

const WIDTH = 13.333;
const HEIGHT = 7.5;

const COLORS = {
  paper: "F5F7F2",
  ink: "0F172A",
  slate: "334155",
  muted: "64748B",
  teal: "0F766E",
  tealDark: "115E59",
  tealSoft: "CCFBF1",
  tealPale: "ECFDF5",
  line: "CBD5E1",
  mint: "D6F5EB",
  sand: "FEF3C7",
  amber: "D97706",
  coral: "FDE2D9",
  red: "B91C1C",
  white: "FFFFFF",
  black: "000000",
};

const FONT_HEAD = "Lato";
const FONT_BODY = "Lato";
const FONT_MONO = "DejaVu Sans Mono";

function round(value) {
  return Math.round(value * 1000) / 1000;
}

function addBackground(slide) {
  slide.background = { color: COLORS.paper };
}

function fitText(text, opts, fontFace = FONT_BODY, extra = {}) {
  const fitted = autoFontSize(text, fontFace, {
    ...opts,
    margin: opts.margin ?? 0,
  });
  const metrics = calcTextBox(fitted.fontSize, {
    text,
    w: fitted.w,
    fontFace,
    bold: fitted.bold,
    italic: fitted.italic,
    margin: fitted.margin,
    padding: fitted.padding,
    leading: fitted.leading,
  });
  return {
    ...fitted,
    h: opts.h ?? round(metrics.h + 0.02),
    ...extra,
  };
}

function addFittedText(slide, text, opts, fontFace = FONT_BODY, extra = {}) {
  const finalOpts = fitText(text, opts, fontFace, extra);
  slide.addText(text, finalOpts);
  return finalOpts;
}

function addKicker(slide, kicker, x, y, w) {
  slide.addText(kicker.toUpperCase(), {
    x,
    y,
    w,
    h: 0.24,
    fontFace: FONT_BODY,
    fontSize: 9,
    bold: true,
    color: COLORS.teal,
    charSpace: 1.2,
    margin: 0,
  });
}

function addTitleBlock(slide, { kicker, title, subtitle, page }) {
  addBackground(slide);
  slide.addShape("roundRect", {
    x: 0.62,
    y: 0.38,
    w: 0.92,
    h: 0.08,
    rectRadius: 0.04,
    line: { color: COLORS.teal, transparency: 100 },
    fill: { color: COLORS.teal },
  });
  addKicker(slide, kicker, 0.68, 0.52, 2.6);
  addFittedText(
    slide,
    title,
    {
      x: 0.68,
      y: 0.8,
      w: 7.6,
      h: 0.78,
      fontSize: 24.5,
      minFontSize: 22.5,
      maxFontSize: 26.5,
      bold: true,
      color: COLORS.ink,
      leading: 1.04,
      valign: "mid",
    },
    FONT_HEAD
  );
  addFittedText(
    slide,
    subtitle,
    {
      x: 0.72,
      y: 1.6,
      w: 6.95,
      h: 0.36,
      fontSize: 12.8,
      minFontSize: 11.5,
      maxFontSize: 13.5,
      color: COLORS.slate,
      leading: 1.16,
      valign: "mid",
    },
    FONT_BODY
  );
  slide.addText(String(page).padStart(2, "0"), {
    x: 12.35,
    y: 0.48,
    w: 0.45,
    h: 0.26,
    fontFace: FONT_BODY,
    fontSize: 9,
    color: COLORS.muted,
    align: "right",
    margin: 0,
  });
}

function addFooter(slide, label) {
  slide.addShape("line", {
    x: 0.7,
    y: 7.05,
    w: 11.95,
    h: 0,
    line: { color: COLORS.line, width: 1 },
  });
  slide.addText(label, {
    x: 0.72,
    y: 7.08,
    w: 4.5,
    h: 0.2,
    fontFace: FONT_BODY,
    fontSize: 8,
    color: COLORS.muted,
    margin: 0,
  });
}

function addCard(slide, config) {
  const {
    x,
    y,
    w,
    h,
    title,
    body,
    titleColor = COLORS.ink,
    bodyColor = COLORS.slate,
    fill = COLORS.white,
    line = COLORS.line,
    accent = COLORS.teal,
    titleFontSize = 15,
    bodyFontSize = 11.5,
    bodyMin = 10,
    bodyMax = 12.5,
    titleMin = 13,
    titleMax = 17,
    radius = 0.12,
  } = config;

  slide.addShape("roundRect", {
    x,
    y,
    w,
    h,
    rectRadius: radius,
    line: { color: line, width: 1.2 },
    fill: { color: fill },
    shadow: safeOuterShadow(COLORS.black, 0.08, 45, 1.5, 1),
  });
  slide.addShape("roundRect", {
    x: x + 0.04,
    y: y + 0.06,
    w: 0.07,
    h: h - 0.12,
    rectRadius: 0.03,
    line: { color: accent, transparency: 100 },
    fill: { color: accent },
  });

  if (title) {
    addFittedText(
      slide,
      title,
      {
        x: x + 0.18,
        y: y + 0.16,
        w: w - 0.32,
        h: 0.42,
        fontSize: titleFontSize,
        minFontSize: titleMin,
        maxFontSize: titleMax,
        bold: true,
        color: titleColor,
        leading: 1.08,
        valign: "mid",
      },
      FONT_HEAD
    );
  }

  if (body) {
    addFittedText(
      slide,
      body,
      {
        x: x + 0.18,
        y: y + (title ? 0.62 : 0.18),
        w: w - 0.32,
        h: h - (title ? 0.78 : 0.34),
        fontSize: bodyFontSize,
        minFontSize: bodyMin,
        maxFontSize: bodyMax,
        color: bodyColor,
        leading: 1.22,
        valign: "top",
      },
      FONT_BODY
    );
  }
}

function addPill(slide, text, x, y, w, opts = {}) {
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h: 0.34,
    rectRadius: 0.12,
    line: { color: opts.line || COLORS.tealSoft, width: 1 },
    fill: { color: opts.fill || COLORS.tealPale },
  });
  slide.addText(text, {
    x,
    y: y + 0.03,
    w,
    h: 0.22,
    fontFace: FONT_BODY,
    fontSize: opts.fontSize || 10,
    bold: opts.bold !== false,
    color: opts.color || COLORS.tealDark,
    align: "center",
    margin: 0,
  });
}

function addMiniMetric(slide, { x, y, w, h, value, label, fill = COLORS.white }) {
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h,
    rectRadius: 0.12,
    line: { color: COLORS.line, width: 1 },
    fill: { color: fill },
  });
  slide.addText(value, {
    x: x + 0.12,
    y: y + 0.16,
    w: w - 0.24,
    h: 0.34,
    fontFace: FONT_HEAD,
    fontSize: 20,
    bold: true,
    color: COLORS.ink,
    margin: 0,
  });
  slide.addText(label, {
    x: x + 0.12,
    y: y + 0.55,
    w: w - 0.24,
    h: 0.3,
    fontFace: FONT_BODY,
    fontSize: 9.5,
    color: COLORS.muted,
    margin: 0,
    leading: 1.1,
  });
}

function addDotItem(slide, { x, y, w, text, color = COLORS.teal, fontSize = 11.5 }) {
  slide.addShape("ellipse", {
    x,
    y: y + 0.07,
    w: 0.11,
    h: 0.11,
    line: { color, transparency: 100 },
    fill: { color },
  });
  addFittedText(
    slide,
    text,
    {
      x: x + 0.18,
      y,
      w,
      h: 0.3,
      fontSize,
      minFontSize: fontSize - 1.5,
      maxFontSize: fontSize + 0.5,
      color: COLORS.slate,
      leading: 1.14,
      valign: "mid",
    },
    FONT_BODY
  );
}

function addSectionBand(slide, text, x, y, w, fill = COLORS.teal) {
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h: 0.3,
    rectRadius: 0.1,
    line: { color: fill, transparency: 100 },
    fill: { color: fill },
  });
  slide.addText(text.toUpperCase(), {
    x,
    y: y + 0.05,
    w,
    h: 0.16,
    fontFace: FONT_BODY,
    fontSize: 8.5,
    bold: true,
    color: COLORS.white,
    margin: 0,
    align: "center",
    charSpace: 0.9,
  });
}

function addSvg(slide, svgString, x, y, w, h) {
  const data = svgToDataUri(svgString);
  slide.addImage({ data, ...imageSizingContain(data, x, y, w, h) });
}

function validateSlide(slide, pptx) {
  warnIfSlideHasOverlaps(slide, pptx, {
    ignoreDecorativeShapes: true,
    muteContainment: true,
  });
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

function architectureSvg() {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1280" height="560" viewBox="0 0 1280 560">
      <style>
        .card { fill: #ffffff; stroke: #cbd5e1; stroke-width: 2; rx: 24; ry: 24; }
        .soft { fill: #ecfdf5; stroke: #99f6e4; stroke-width: 2; rx: 24; ry: 24; }
        .text { font-family: Lato, Arial, sans-serif; font-size: 24px; fill: #0f172a; font-weight: 700; }
        .body { font-family: Lato, Arial, sans-serif; font-size: 18px; fill: #334155; }
        .small { font-family: Lato, Arial, sans-serif; font-size: 16px; font-weight: 700; }
        .arrow { stroke: #0f766e; stroke-width: 4; fill: none; stroke-linecap: round; stroke-linejoin: round; }
      </style>
      <rect x="60" y="40" width="1160" height="480" rx="32" ry="32" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <rect class="card" x="100" y="95" width="180" height="92" rx="24" ry="24"/>
      <rect class="card" x="345" y="95" width="200" height="92" rx="24" ry="24"/>
      <rect class="card" x="610" y="95" width="165" height="92" rx="24" ry="24"/>
      <rect class="soft" x="840" y="72" width="170" height="92" rx="24" ry="24"/>
      <rect class="soft" x="840" y="194" width="170" height="92" rx="24" ry="24"/>
      <rect class="card" x="1075" y="145" width="130" height="92" rx="24" ry="24"/>
      <rect class="card" x="600" y="348" width="190" height="92" rx="24" ry="24"/>
      <rect class="card" x="875" y="348" width="190" height="92" rx="24" ry="24"/>
      <rect class="card" x="1120" y="348" width="100" height="92" rx="24" ry="24"/>

      <text class="text" x="142" y="148">User Question</text>
      <text class="text" x="395" y="148">Frontend</text>
      <text class="body" x="395" y="176">React + Vite UI</text>
      <text class="text" x="648" y="148">POST /api/qa</text>
      <text class="text" x="882" y="124">ClinicalTrials</text>
      <text class="body" x="883" y="151">status-aware search</text>
      <text class="text" x="886" y="245">PubMed</text>
      <text class="body" x="887" y="272">esearch → esummary → efetch</text>
      <text class="text" x="1090" y="199">Cache</text>
      <text class="body" x="1079" y="227">SQLite TTL</text>

      <text class="text" x="630" y="402">Hybrid Rerank</text>
      <text class="body" x="632" y="430">source rank + lexical overlap + optional embeddings</text>
      <text class="text" x="905" y="403">Structured Answer</text>
      <text class="body" x="915" y="432">intent + grounded synthesis</text>
      <text class="text" x="1135" y="403">Trace</text>
      <text class="body" x="1128" y="431">citations</text>

      <path class="arrow" d="M280 141 H345"/>
      <path class="arrow" d="M545 141 H610"/>
      <path class="arrow" d="M775 141 H840"/>
      <path class="arrow" d="M775 141 H1010 V191 H1075"/>
      <path class="arrow" d="M775 141 V240 H840"/>
      <path class="arrow" d="M925 286 V348 H695"/>
      <path class="arrow" d="M1090 237 V302 H730 V348"/>
      <path class="arrow" d="M1010 118 H1075"/>
      <path class="arrow" d="M790 394 H875"/>
      <path class="arrow" d="M1065 394 H1120"/>

      <rect x="95" y="470" width="220" height="24" rx="12" ry="12" fill="#ccfbf1"/>
      <text class="small" x="118" y="487" fill="#115e59">qa.py orchestrates the full path</text>
      <rect x="340" y="470" width="260" height="24" rx="12" ry="12" fill="#e2e8f0"/>
      <text class="small" x="360" y="487" fill="#334155">trace exposes every major stage</text>
      <rect x="620" y="470" width="340" height="24" rx="12" ry="12" fill="#fef3c7"/>
      <text class="small" x="642" y="487" fill="#92400e">model is constrained after retrieval</text>
    </svg>
  `;
}

function pipelineSvg() {
  const stages = [
    ["cache", "#ecfdf5"],
    ["intent", "#e2f2ff"],
    ["clinical_trials_retrieval", "#ecfdf5"],
    ["pubmed_retrieval", "#eff6ff"],
    ["rerank", "#f8fafc"],
    ["answer_generation", "#fef3c7"],
    ["citation_validation", "#fee2e2"],
    ["final_response", "#ecfccb"],
  ];
  const blocks = stages
    .map(([label, fill], index) => {
      const x = 36 + index * 150;
      return `
        <rect x="${x}" y="82" width="132" height="90" rx="18" ry="18" fill="${fill}" stroke="#cbd5e1" stroke-width="2"/>
        <text x="${x + 12}" y="112" font-family="DejaVu Sans Mono, monospace" font-size="15" fill="#0f172a">${label}</text>
        <text x="${x + 16}" y="138" font-family="Lato, Arial, sans-serif" font-size="13" fill="#64748b">trace stage id</text>
      `;
    })
    .join("");
  const arrows = Array.from({ length: 7 })
    .map((_, index) => {
      const x1 = 168 + index * 150;
      const x2 = 186 + index * 150;
      return `<path d="M${x1} 127 H${x2}" stroke="#0f766e" stroke-width="4" stroke-linecap="round"/>`;
    })
    .join("");
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1240" height="320" viewBox="0 0 1240 320">
      <rect x="10" y="24" width="1220" height="272" rx="28" ry="28" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
      ${blocks}
      ${arrows}
      <text x="48" y="228" font-family="Lato, Arial, sans-serif" font-size="18" font-weight="700" fill="#0f172a">What the trace gives you:</text>
      <text x="48" y="257" font-family="Lato, Arial, sans-serif" font-size="16" fill="#334155">route, cache hit or miss, timings, stage cards, and expandable raw JSON for every step.</text>
    </svg>
  `;
}

function questionMatrixSvg() {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1220" height="400" viewBox="0 0 1220 400">
      <style>
        .h { font-family: Lato, Arial, sans-serif; font-size: 17px; font-weight: 700; }
        .b { font-family: Lato, Arial, sans-serif; font-size: 15px; fill: #334155; }
        .m { font-family: DejaVu Sans Mono, monospace; font-size: 14px; fill: #0f172a; }
      </style>
      <rect x="16" y="18" width="1188" height="364" rx="26" ry="26" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="42" y="48" width="1136" height="44" rx="16" ry="16" fill="#0f766e"/>
      <text class="h" x="64" y="76" fill="#ffffff">Example question</text>
      <text class="h" x="740" y="76" fill="#ffffff">Route</text>
      <text class="h" x="855" y="76" fill="#ffffff">Evidence</text>
      <text class="h" x="1025" y="76" fill="#ffffff">Why it matters</text>

      <rect x="42" y="108" width="1136" height="76" rx="18" ry="18" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <text class="b" x="64" y="139">Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?</text>
      <rect x="734" y="122" width="82" height="28" rx="14" ry="14" fill="#ccfbf1"/>
      <text class="h" x="757" y="141" fill="#115e59">trials</text>
      <text class="m" x="845" y="139">NCT...</text>
      <text class="b" x="1025" y="139">status-aware query planning</text>

      <rect x="42" y="194" width="1136" height="76" rx="18" ry="18" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <text class="b" x="64" y="225">What does the published literature say about the safety of semaglutide in adults with obesity?</text>
      <rect x="726" y="208" width="98" height="28" rx="14" ry="14" fill="#dbeafe"/>
      <text class="h" x="748" y="227" fill="#1d4ed8">pubmed</text>
      <text class="m" x="845" y="225">PMID...</text>
      <text class="b" x="1025" y="225">abstract-grounded evidence</text>

      <rect x="42" y="280" width="1136" height="76" rx="18" ry="18" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <text class="b" x="64" y="311">What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?</text>
      <rect x="721" y="294" width="108" height="28" rx="14" ry="14" fill="#fef3c7"/>
      <text class="h" x="737" y="313" fill="#92400e">blended</text>
      <text class="m" x="845" y="311">NCT + PMID</text>
      <text class="b" x="1025" y="311">hardest synthesis case</text>
    </svg>
  `;
}

function buildDeck() {
  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: "QA_WIDE", width: WIDTH, height: HEIGHT });
  pptx.layout = "QA_WIDE";
  pptx.author = "OpenAI Codex";
  pptx.company = "OpenAI";
  pptx.subject = "Clinical QA MVP presentation";
  pptx.title = "Clinical QA MVP Grounded in ClinicalTrials.gov and PubMed";
  pptx.lang = "en-US";
  pptx.theme = {
    headFontFace: FONT_HEAD,
    bodyFontFace: FONT_BODY,
    lang: "en-US",
  };

  let page = 1;

  {
    const slide = pptx.addSlide();
    addBackground(slide);
    slide.addShape("roundRect", {
      x: 0.68,
      y: 0.62,
      w: 0.95,
      h: 0.08,
      rectRadius: 0.04,
      line: { color: COLORS.teal, transparency: 100 },
      fill: { color: COLORS.teal },
    });
    addKicker(slide, "Clinical QA MVP", 0.72, 0.78, 3);
    addFittedText(
      slide,
      "Grounded Clinical QA with ClinicalTrials.gov and PubMed",
      {
        x: 0.72,
        y: 1.15,
        w: 6.6,
        h: 1.15,
        fontSize: 29,
        minFontSize: 25,
        maxFontSize: 31,
        bold: true,
        color: COLORS.ink,
        leading: 1.03,
      },
      FONT_HEAD
    );
    addFittedText(
      slide,
      "A working local MVP for evidence-grounded retrieval, bounded synthesis, inspectable citations, and conservative fallback behavior.",
      {
        x: 0.74,
        y: 2.43,
        w: 6.15,
        h: 0.72,
        fontSize: 14.5,
        minFontSize: 13,
        maxFontSize: 15.5,
        color: COLORS.slate,
        leading: 1.26,
      },
      FONT_BODY
    );
    addPill(slide, "25-30 minute walkthrough", 0.76, 3.25, 2.15, {
      fill: COLORS.tealSoft,
      line: COLORS.tealSoft,
    });
    addPill(slide, "FastAPI + React + SQLite", 2.98, 3.25, 2.32, {
      fill: COLORS.white,
      line: COLORS.line,
      color: COLORS.slate,
    });

    addCard(slide, {
      x: 7.45,
      y: 0.82,
      w: 2.45,
      h: 1.16,
      title: "What it is",
      body: "A single-turn clinical QA app that retrieves live evidence and returns structured answers with citations.",
      fill: COLORS.white,
      accent: COLORS.teal,
    });
    addCard(slide, {
      x: 10.02,
      y: 0.82,
      w: 2.63,
      h: 1.16,
      title: "What it is not",
      body: "Not a diagnosis engine. The model does not replace a clinician or act as the source of truth.",
      fill: COLORS.white,
      accent: COLORS.red,
      line: "F1B7B7",
    });
    addMiniMetric(slide, {
      x: 7.48,
      y: 2.2,
      w: 1.22,
      h: 1.02,
      value: "2",
      label: "live evidence sources",
      fill: COLORS.tealPale,
    });
    addMiniMetric(slide, {
      x: 8.84,
      y: 2.2,
      w: 1.22,
      h: 1.02,
      value: "8",
      label: "trace stages in UI",
      fill: COLORS.white,
    });
    addMiniMetric(slide, {
      x: 10.2,
      y: 2.2,
      w: 1.22,
      h: 1.02,
      value: "30",
      label: "backend automated tests",
      fill: COLORS.white,
    });
    addMiniMetric(slide, {
      x: 11.56,
      y: 2.2,
      w: 1.06,
      h: 1.02,
      value: "5",
      label: "integration flows",
      fill: COLORS.tealPale,
    });

    slide.addShape("roundRect", {
      x: 0.72,
      y: 4.2,
      w: 11.96,
      h: 1.9,
      rectRadius: 0.18,
      line: { color: COLORS.line, width: 1.2 },
      fill: { color: COLORS.white },
      shadow: safeOuterShadow(COLORS.black, 0.08, 45, 1.5, 1),
    });
    addSectionBand(slide, "Design philosophy", 0.94, 4.42, 1.65);
    addFittedText(
      slide,
      "The model is not the source of truth. Retrieved evidence is the source of truth, and the product is designed to make that visible.",
      {
        x: 0.98,
        y: 4.82,
        w: 7.0,
        h: 0.64,
        fontSize: 16.5,
        minFontSize: 15,
        maxFontSize: 17,
        bold: true,
        color: COLORS.ink,
        leading: 1.18,
      },
      FONT_HEAD
    );
    addDotItem(slide, {
      x: 8.25,
      y: 4.7,
      w: 3.6,
      text: "Provider-neutral: OpenAI or local vLLM through the same backend path.",
    });
    addDotItem(slide, {
      x: 8.25,
      y: 5.12,
      w: 3.6,
      text: "Inspectable UI: source drawer, grouped citations, and full pipeline trace.",
    });
    addDotItem(slide, {
      x: 8.25,
      y: 5.54,
      w: 3.6,
      text: "Conservative failure handling: extractive fallback if generation or citation validation fails.",
      color: COLORS.red,
    });
    addFooter(slide, "Clinical QA MVP overview");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Talk map",
      title: "How the 30-minute walkthrough is structured",
      subtitle:
        "The deck follows the implemented code path: product framing, request flow, source-specific retrieval, grounding, and production tradeoffs.",
      page,
    });

    const sections = [
      ["01", "Product and UX", "4 min", "What the user sees, what the frontend exposes, and the deliberate non-goals.", COLORS.tealPale],
      ["02", "Request lifecycle", "7 min", "From POST /api/qa through cache, intent extraction, retrieval, reranking, synthesis, and trace assembly.", COLORS.white],
      ["03", "Retrieval by source", "8 min", "Why ClinicalTrials.gov and PubMed use different query planning, normalization, and snippet shapes.", COLORS.white],
      ["04", "Grounding and safeguards", "6 min", "Structured outputs, citation normalization, degraded mode, and why the model stays constrained.", COLORS.tealPale],
      ["05", "Tradeoffs and next steps", "5 min", "What this MVP intentionally does not solve yet and what I would build next.", COLORS.white],
    ];

    sections.forEach((section, index) => {
      const [n, title, time, body, fill] = section;
      const x = index < 3 ? 0.82 + index * 4.16 : 2.92 + (index - 3) * 4.16;
      const y = index < 3 ? 2.2 : 4.56;
      slide.addShape("roundRect", {
        x,
        y,
        w: 3.45,
        h: 1.84,
        rectRadius: 0.16,
        line: { color: COLORS.line, width: 1.2 },
        fill: { color: fill },
      });
      slide.addText(n, {
        x: x + 0.18,
        y: y + 0.14,
        w: 0.45,
        h: 0.25,
        fontFace: FONT_MONO,
        fontSize: 12,
        color: COLORS.teal,
        margin: 0,
      });
      addPill(slide, time, x + 2.42, y + 0.14, 0.78, {
        fill: COLORS.sand,
        line: COLORS.sand,
        color: COLORS.amber,
        fontSize: 9,
      });
      addFittedText(
        slide,
        title,
        {
          x: x + 0.18,
          y: y + 0.56,
          w: 2.95,
          h: 0.28,
          fontSize: 15.5,
          minFontSize: 14,
          maxFontSize: 16.5,
          bold: true,
          color: COLORS.ink,
          leading: 1.08,
        },
        FONT_HEAD
      );
      addFittedText(
        slide,
        body,
        {
          x: x + 0.18,
          y: y + 0.94,
          w: 2.98,
          h: 0.64,
          fontSize: 11.3,
          minFontSize: 10.2,
          maxFontSize: 12,
          color: COLORS.slate,
          leading: 1.22,
        },
        FONT_BODY
      );
    });

    addCard(slide, {
      x: 0.82,
      y: 6.42,
      w: 12,
      h: 0.42,
      title: "",
      body: "Framing line for the interview: this is an implemented MVP walkthrough, not a purely hypothetical architecture whiteboard.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.2,
      bodyMin: 10.6,
      bodyMax: 11.8,
    });
    addFooter(slide, "Agenda aligned to the implemented repo");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Frontend",
      title: "The user experience is optimized for inspectability, not chat polish",
      subtitle:
        "The React app accepts one clinical question at a time, renders a structured answer, and keeps the underlying evidence visible.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.18,
      w: 3.5,
      h: 3.88,
      title: "What the user can control",
      body:
        "Question input\nRecruiting trials only toggle\nRecent literature only toggle\nMax sources slider (3-8)\nExample questions for the three route families",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 12,
      bodyMin: 10.8,
      bodyMax: 12.2,
    });

    slide.addShape("roundRect", {
      x: 4.62,
      y: 2.18,
      w: 7.86,
      h: 3.88,
      rectRadius: 0.18,
      line: { color: COLORS.line, width: 1.2 },
      fill: { color: COLORS.white },
      shadow: safeOuterShadow(COLORS.black, 0.08, 45, 1.5, 1),
    });
    addSectionBand(slide, "UI anatomy", 4.88, 2.36, 1.2);
    addCard(slide, {
      x: 4.9,
      y: 2.76,
      w: 2.22,
      h: 1.18,
      title: "Direct answer",
      body: "Single answer block with degraded-mode badge when the system falls back.",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 10.3,
      bodyMin: 9.6,
    });
    addCard(slide, {
      x: 7.27,
      y: 2.76,
      w: 2.22,
      h: 1.18,
      title: "Why this answer",
      body: "Evidence bullets distilled from the selected snippets.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 10.3,
      bodyMin: 9.6,
    });
    addCard(slide, {
      x: 9.64,
      y: 2.76,
      w: 2.22,
      h: 1.18,
      title: "Limitations",
      body: "Uncertainty is separated from the main answer rather than hidden inside it.",
      fill: COLORS.coral,
      accent: COLORS.red,
      line: "F1B7B7",
      bodyFontSize: 10.1,
      bodyMin: 9.2,
    });
    addCard(slide, {
      x: 4.9,
      y: 4.18,
      w: 3.72,
      h: 1.46,
      title: "Grouped citations",
      body: "Citations are grouped by source type and each card opens a source drawer with cached metadata plus all available snippets.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 10.8,
    });
    addCard(slide, {
      x: 8.8,
      y: 4.18,
      w: 3.06,
      h: 1.46,
      title: "Pipeline trace drawer",
      body: "Users can inspect route, cache hit, total ms, stage metrics, stage cards, and raw JSON for every pipeline step.",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 10.5,
    });

    addDotItem(slide, {
      x: 0.98,
      y: 6.38,
      w: 11.2,
      text: "The frontend stays thin by design. It submits the request, renders the structured response, and exposes inspectability through drawers instead of hiding the pipeline.",
      fontSize: 11.8,
    });
    addFooter(slide, "Frontend behavior from frontend/src/App.tsx");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Architecture",
      title: "The system is modular: retrieval, reranking, synthesis, validation, and trace assembly are separate steps",
      subtitle:
        "The orchestration sits in qa.py, while source-specific logic and provider logic stay isolated in their own service modules.",
      page,
    });
    addSvg(slide, architectureSvg(), 0.72, 2.0, 11.95, 3.45);
    addCard(slide, {
      x: 0.84,
      y: 5.74,
      w: 3.65,
      h: 0.92,
      title: "Core backend modules",
      body: "qa.py, clinicaltrials.py, pubmed.py, rerank.py, llm_service.py, cache.py",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 10.5,
    });
    addCard(slide, {
      x: 4.68,
      y: 5.74,
      w: 3.77,
      h: 0.92,
      title: "Public API surface",
      body: "POST /api/qa, GET /api/sources/{source_type}/{source_id}, GET /api/health",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 10.3,
    });
    addCard(slide, {
      x: 8.66,
      y: 5.74,
      w: 3.83,
      h: 0.92,
      title: "MVP boundary",
      body: "Single-turn product, live retrieval + TTL cache, abstract-grounded PubMed baseline, bounded evidence window",
      fill: COLORS.white,
      accent: COLORS.amber,
      line: COLORS.sand,
      bodyFontSize: 10.2,
    });
    addFooter(slide, "End-to-end request path and module boundaries");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Trace",
      title: "The request lifecycle is visible as real pipeline stages in the product",
      subtitle:
        "If an answer is wrong, the trace makes it possible to see whether the failure came from routing, retrieval, ranking, generation, or citation handling.",
      page,
    });
    addSvg(slide, pipelineSvg(), 0.72, 2.08, 11.9, 2.1);
    addCard(slide, {
      x: 0.84,
      y: 4.42,
      w: 3.66,
      h: 1.45,
      title: "Why the trace matters",
      body: "Bad clinical QA systems often fail silently. This one exposes stage summaries, metrics, cards, and raw JSON so debugging stays concrete.",
      fill: COLORS.white,
      accent: COLORS.teal,
    });
    addCard(slide, {
      x: 4.72,
      y: 4.42,
      w: 3.66,
      h: 1.45,
      title: "Trace summary fields",
      body: "route\ncache_hit\ntotal_ms\ndegraded\noptional degraded_reason",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 11.4,
    });
    addCard(slide, {
      x: 8.6,
      y: 4.42,
      w: 3.88,
      h: 1.45,
      title: "Stage payload examples",
      body: "query params for retrieval\nsearch term for PubMed\ntop reranked snippets\ncitation ids and validation status",
      fill: COLORS.white,
      accent: COLORS.teal,
    });
    addDotItem(slide, {
      x: 0.98,
      y: 6.32,
      w: 11.2,
      text: "This is a product feature, not just a developer convenience. The UI deliberately surfaces evidence provenance and processing trace to build trust.",
      fontSize: 11.7,
    });
    addFooter(slide, "Trace stages come directly from backend/app/services/qa.py");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "ClinicalTrials.gov",
      title: "Trial retrieval is source-aware rather than generic full-text search",
      subtitle:
        "The backend preserves trial semantics such as recruiting status, phase, eligibility, and outcomes instead of flattening everything into one search string.",
      page,
    });
    addCard(slide, {
      x: 0.82,
      y: 2.12,
      w: 4.16,
      h: 3.88,
      title: "Query planning",
      body:
        "Primary structured fields:\nquery.cond\nquery.intr\nquery.term fallback\n\nStatus-aware behavior:\nrecruiting questions apply RECRUITING at retrieval time\nongoing questions widen the status window",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.4,
    });
    addCard(slide, {
      x: 5.16,
      y: 2.12,
      w: 3.28,
      h: 3.88,
      title: "Normalized trial snippets",
      body:
        "status\nsummary\neligibility\noutcomes\n\nEach study becomes a NormalizedSource with stable snippet ids and source metadata preserved.",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 11.4,
    });
    addCard(slide, {
      x: 8.64,
      y: 2.12,
      w: 3.88,
      h: 1.78,
      title: "Example routed question",
      body: "Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 10.8,
    });
    addCard(slide, {
      x: 8.64,
      y: 4.02,
      w: 3.88,
      h: 1.98,
      title: "Real bug that got fixed",
      body:
        "Earlier logic could retrieve only a few trials and then filter for recruiting status afterward. That could truncate away the true recruiting matches and produce a false no-trials answer.",
      fill: COLORS.coral,
      accent: COLORS.red,
      line: "F1B7B7",
      bodyFontSize: 10.55,
    });
    addFooter(slide, "ClinicalTrials planning and normalization from backend/app/services/clinicaltrials.py");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "PubMed",
      title: "PubMed follows a different retrieval path and stays honest about abstract-level grounding",
      subtitle:
        "This branch builds PubMed-style title or abstract clauses, retrieves PMIDs first, then expands into metadata plus abstract chunks.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.14,
      w: 3.78,
      h: 3.9,
      title: "Three-step retrieval chain",
      body:
        "1. esearch\nFind candidate PMIDs\n\n2. esummary\nPull titles, journals, authors, publication metadata\n\n3. efetch\nParse abstract text into sentence-level chunks",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.2,
    });
    addCard(slide, {
      x: 4.86,
      y: 2.14,
      w: 3.72,
      h: 3.9,
      title: "Query inputs",
      body:
        "condition terms\nintervention terms\npopulation terms\noutcome terms\n\nThese become conservative title or abstract clauses, optionally with a recent-publication date filter.",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 11.2,
    });
    addCard(slide, {
      x: 8.82,
      y: 2.14,
      w: 3.62,
      h: 1.74,
      title: "Snippet types",
      body: "title\nmetadata\nabstract_1 ... abstract_n",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.8,
    });
    addCard(slide, {
      x: 8.82,
      y: 4.02,
      w: 3.62,
      h: 2.02,
      title: "Current limitation",
      body:
        "The MVP is abstract-grounded unless richer article text is available. That limitation is surfaced directly in answer limitations rather than hidden.",
      fill: COLORS.sand,
      accent: COLORS.amber,
      line: COLORS.sand,
      bodyFontSize: 10.8,
    });
    addFooter(slide, "PubMed flow from backend/app/services/pubmed.py");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Reranking",
      title: "The evidence window is deliberately bounded before the model sees it",
      subtitle:
        "Instead of building a full vector database first, the MVP reranks live-retrieved snippets and enforces source diversity.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.12,
      w: 4.0,
      h: 3.8,
      title: "Hybrid scoring formula",
      body:
        "0.35 source rank\n0.35 keyword overlap\n0.30 embedding similarity when embeddings are enabled\n\nIf embeddings are disabled, the weights renormalize automatically instead of breaking the pipeline.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.2,
    });
    addCard(slide, {
      x: 5.08,
      y: 2.12,
      w: 3.44,
      h: 3.8,
      title: "Diversity control",
      body:
        "Top-k selection caps each source at two snippets first, then backfills from overflow. That prevents one paper or one trial from dominating the answer window.",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 11.1,
    });
    addCard(slide, {
      x: 8.76,
      y: 2.12,
      w: 3.66,
      h: 1.7,
      title: "Trial snippets",
      body: "status\nsummary\neligibility\noutcomes",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.8,
    });
    addCard(slide, {
      x: 8.76,
      y: 3.98,
      w: 3.66,
      h: 1.94,
      title: "Literature snippets",
      body: "title\nmetadata\nabstract chunks\n\nDifferent snippet shapes preserve source semantics and improve explanation quality.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 10.9,
    });
    addFooter(slide, "HybridReranker behavior from backend/app/services/rerank.py");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Grounding",
      title: "The LLM is a constrained synthesizer, not a source of truth",
      subtitle:
        "The same OpenAI-compatible interface supports OpenAI and local vLLM, but generation only happens after evidence retrieval and reranking.",
      page,
    });
    addCard(slide, {
      x: 0.82,
      y: 2.1,
      w: 3.7,
      h: 1.72,
      title: "LLM use #1: intent extraction",
      body:
        "Outputs QuestionIntent with route, focus, extracted condition or intervention or population or outcome terms, and merged filters.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 10.9,
    });
    addCard(slide, {
      x: 0.82,
      y: 4.0,
      w: 3.7,
      h: 1.92,
      title: "LLM use #2: answer drafting",
      body:
        "Outputs QAAnswerDraft with direct_answer, why_this_answer, limitations, and citation_ids grounded in retrieved snippets.",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 10.9,
    });
    addCard(slide, {
      x: 4.72,
      y: 2.1,
      w: 3.72,
      h: 3.82,
      title: "Provider-neutral config",
      body:
        "CHAT_PROVIDER = openai | vllm\nEMBED_PROVIDER = openai | vllm | none\n\nOne backend path can demo against hosted models or a local GPU server without rewriting the pipeline.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.2,
    });
    addCard(slide, {
      x: 8.64,
      y: 2.1,
      w: 3.84,
      h: 3.82,
      title: "Safeguard ladder",
      body:
        "strip residual thinking text\nnormalize source ids back to snippet ids\nvalidate citation ids against retrieved evidence\nretry invalid structured output once\nfallback to extractive answer if support is still weak",
      fill: COLORS.coral,
      accent: COLORS.red,
      line: "F1B7B7",
      bodyFontSize: 10.9,
    });
    addFooter(slide, "LLM orchestration and fallbacks from backend/app/services/llm_service.py and qa.py");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Examples",
      title: "Three real questions exercise the three route families",
      subtitle:
        "These questions already exist in the frontend as example prompts and together they cover trials-first, PubMed-first, and blended retrieval.",
      page,
    });
    addSvg(slide, questionMatrixSvg(), 0.8, 2.05, 11.9, 3.55);
    addDotItem(slide, {
      x: 0.98,
      y: 6.02,
      w: 11.2,
      text: "The blended question is the hardest case. Retrieval is already solid, but answer planning across both source families is still the biggest open product challenge.",
      fontSize: 11.8,
      color: COLORS.amber,
    });
    addFooter(slide, "Example prompts come directly from frontend/src/App.tsx");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Engineering quality",
      title: "Trust comes from cache hygiene, traceability, and conservative degraded behavior",
      subtitle:
        "The repo is not just a demo path. It includes caching rules, source detail endpoints, runtime-aware cache keys, and a backend test suite.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.16,
      w: 3.74,
      h: 3.78,
      title: "Cache discipline",
      body:
        "The query cache key includes normalized question, filters, max_sources, and runtime context. That prevents the same question under OpenAI and vLLM from incorrectly sharing a cached answer.",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 10.95,
    });
    addCard(slide, {
      x: 4.82,
      y: 2.16,
      w: 3.52,
      h: 3.78,
      title: "Operational endpoints",
      body:
        "GET /api/health\nreports provider readiness and cache cleanup state\n\nGET /api/sources/{source_type}/{source_id}\nexposes cached normalized source data for citation drill-down",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 10.95,
    });
    addCard(slide, {
      x: 8.58,
      y: 2.16,
      w: 3.9,
      h: 3.78,
      title: "Tests and degraded modes",
      body:
        "30 automated backend tests\n5 integration flows: trials-first, pubmed-first, blended, no results, provider failure fallback\n\nIf the provider is unavailable or citations fail validation, the system returns an extractive answer instead of a broken one.",
      fill: COLORS.white,
      accent: COLORS.red,
      line: "F1B7B7",
      bodyFontSize: 10.7,
    });
    addFooter(slide, "Cache behavior from backend/app/services/cache.py; routes from backend/app/main.py");
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Tradeoffs",
      title: "This MVP is intentionally small, debuggable, and honest about its limits",
      subtitle:
        "The current architecture solves source-aware retrieval and grounded synthesis first. Productionization would expand indexing, evaluation, and blended-answer planning.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.12,
      w: 5.72,
      h: 3.98,
      title: "Current choices",
      body:
        "Live retrieval + TTL cache instead of a full offline ingestion pipeline\nBounded hybrid reranking instead of a vector database\nAbstract-grounded PubMed baseline instead of implying full-text depth\nSingle-turn QA UI instead of multi-turn chat",
      fill: COLORS.white,
      accent: COLORS.teal,
      bodyFontSize: 11.4,
    });
    addCard(slide, {
      x: 6.78,
      y: 2.12,
      w: 5.7,
      h: 3.98,
      title: "What I would build next",
      body:
        "1. stronger offline indexing for latency, recall, and observability\n2. a layered evaluation suite for route correctness, retrieval quality, snippet relevance, citation validity, and answer usefulness\n3. better answer planning and evidence budgeting for blended questions\n4. a richer full-text pipeline where licensing and availability allow it",
      fill: COLORS.tealPale,
      accent: COLORS.teal,
      bodyFontSize: 11.1,
    });
    slide.addShape("roundRect", {
      x: 0.86,
      y: 6.34,
      w: 11.62,
      h: 0.54,
      rectRadius: 0.15,
      line: { color: COLORS.tealDark, transparency: 100 },
      fill: { color: COLORS.tealDark },
    });
    addFittedText(
      slide,
      "Closing line: the model is not the source of truth. The retrieved evidence is the source of truth, and the system should make that visible.",
      {
        x: 1.05,
        y: 6.47,
        w: 11.18,
        h: 0.2,
        fontSize: 12.4,
        minFontSize: 11.6,
        maxFontSize: 12.8,
        bold: true,
        color: COLORS.white,
        align: "center",
      },
      FONT_HEAD
    );
    addFooter(slide, "Closing tradeoffs and next steps");
    validateSlide(slide, pptx);
  }

  return pptx;
}

async function main() {
  const outDir = path.join(__dirname, "dist");
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, "clinical_qa_mvp_presentation.pptx");
  const pptx = buildDeck();
  await pptx.writeFile({ fileName: outPath, compression: true });
  console.log(`Wrote ${outPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
