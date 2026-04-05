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
  paper: "F7F5EF",
  paperSoft: "F2F0E8",
  white: "FFFFFF",
  ink: "111827",
  slate: "334155",
  muted: "64748B",
  teal: "0F766E",
  tealDark: "115E59",
  tealPale: "DFF6F2",
  tealSoft: "BEEDE4",
  tealLine: "94D5CB",
  bluePale: "E6F0FF",
  blue: "2563EB",
  amberPale: "FEF3C7",
  amber: "B45309",
  rosePale: "FDE7E7",
  red: "B91C1C",
  line: "CBD5E1",
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
  slide.addShape("rect", {
    x: 0,
    y: 0,
    w: WIDTH,
    h: HEIGHT,
    line: { color: COLORS.paper },
    fill: { color: COLORS.paper },
  });
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

function addTitleBlock(slide, { kicker, title, subtitle, page }) {
  addBackground(slide);
  slide.addShape("roundRect", {
    x: 0.62,
    y: 0.42,
    w: 1.04,
    h: 0.08,
    rectRadius: 0.04,
    line: { color: COLORS.teal, transparency: 100 },
    fill: { color: COLORS.teal },
  });
  slide.addText(kicker.toUpperCase(), {
    x: 0.7,
    y: 0.56,
    w: 2.6,
    h: 0.22,
    fontFace: FONT_BODY,
    fontSize: 8.8,
    bold: true,
    color: COLORS.teal,
    charSpace: 1.1,
    margin: 0,
  });
  addFittedText(
    slide,
    title,
    {
      x: 0.7,
      y: 0.84,
      w: 8.2,
      h: 0.76,
      fontSize: 24,
      minFontSize: 21.5,
      maxFontSize: 26.2,
      bold: true,
      color: COLORS.ink,
      leading: 1.04,
    },
    FONT_HEAD
  );
  addFittedText(
    slide,
    subtitle,
    {
      x: 0.74,
      y: 1.62,
      w: 7.7,
      h: 0.34,
      fontSize: 12.4,
      minFontSize: 11.2,
      maxFontSize: 13,
      color: COLORS.slate,
      leading: 1.12,
    },
    FONT_BODY
  );
  slide.addText(String(page).padStart(2, "0"), {
    x: 12.3,
    y: 0.5,
    w: 0.45,
    h: 0.22,
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
    y: 7.02,
    w: 11.95,
    h: 0,
    line: { color: COLORS.line, width: 1 },
  });
  slide.addText(label, {
    x: 0.72,
    y: 7.08,
    w: 4.9,
    h: 0.18,
    fontFace: FONT_BODY,
    fontSize: 8,
    color: COLORS.muted,
    margin: 0,
  });
}

function addCard(slide, {
  x,
  y,
  w,
  h,
  title,
  body,
  fill = COLORS.white,
  line = COLORS.line,
  accent = COLORS.teal,
  titleFontSize = 15,
  titleMin = 13,
  titleMax = 16.5,
  bodyFontSize = 11.2,
  bodyMin = 10,
  bodyMax = 12,
  bodyColor = COLORS.slate,
  titleColor = COLORS.ink,
}) {
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h,
    rectRadius: 0.16,
    line: { color: line, width: 1.15 },
    fill: { color: fill },
    shadow: safeOuterShadow(COLORS.black, 0.07, 45, 1.5, 1),
  });
  slide.addShape("roundRect", {
    x: x + 0.04,
    y: y + 0.08,
    w: 0.08,
    h: h - 0.16,
    rectRadius: 0.04,
    line: { color: accent, transparency: 100 },
    fill: { color: accent },
  });
  if (title) {
    addFittedText(
      slide,
      title,
      {
        x: x + 0.2,
        y: y + 0.16,
        w: w - 0.3,
        h: 0.3,
        fontSize: titleFontSize,
        minFontSize: titleMin,
        maxFontSize: titleMax,
        bold: true,
        color: titleColor,
        leading: 1.06,
      },
      FONT_HEAD
    );
  }
  if (body) {
    addFittedText(
      slide,
      body,
      {
        x: x + 0.2,
        y: y + (title ? 0.52 : 0.18),
        w: w - 0.3,
        h: h - (title ? 0.7 : 0.32),
        fontSize: bodyFontSize,
        minFontSize: bodyMin,
        maxFontSize: bodyMax,
        color: bodyColor,
        leading: 1.18,
        valign: "top",
      },
      FONT_BODY
    );
  }
}

function addPill(slide, text, x, y, w, {
  fill = COLORS.tealPale,
  line = COLORS.tealPale,
  color = COLORS.tealDark,
  fontSize = 9.5,
} = {}) {
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h: 0.32,
    rectRadius: 0.12,
    line: { color: line, width: 1 },
    fill: { color: fill },
  });
  slide.addText(text, {
    x,
    y: y + 0.035,
    w,
    h: 0.18,
    fontFace: FONT_BODY,
    fontSize,
    bold: true,
    color,
    align: "center",
    margin: 0,
  });
}

function addBulletList(slide, items, {
  x,
  y,
  w,
  h,
  fontSize = 11,
  minFontSize = 10,
  maxFontSize = 11.5,
  color = COLORS.slate,
}) {
  const runs = [];
  items.forEach((item, index) => {
    if (index > 0) {
      runs.push({ text: "\n" });
    }
    runs.push({
      text: item,
      options: {
        bullet: { indent: 12 },
      },
    });
  });
  const opts = fitText(runs, {
    x,
    y,
    w,
    h,
    fontSize,
    minFontSize,
    maxFontSize,
    color,
    margin: 0,
    breakLine: false,
    leading: 1.18,
    valign: "top",
    paraSpaceAfterPt: 5,
  });
  slide.addText(runs, {
    ...opts,
    fontFace: FONT_BODY,
    color,
  });
}

function addCodeStrip(slide, label, body) {
  slide.addShape("roundRect", {
    x: 0.82,
    y: 6.38,
    w: 11.62,
    h: 0.46,
    rectRadius: 0.14,
    line: { color: COLORS.line, width: 1 },
    fill: { color: COLORS.white },
  });
  slide.addText(`${label}:`, {
    x: 1.02,
    y: 6.5,
    w: 0.82,
    h: 0.16,
    fontFace: FONT_BODY,
    fontSize: 8.6,
    bold: true,
    color: COLORS.tealDark,
    margin: 0,
  });
  slide.addText(body, {
    x: 2.12,
    y: 6.5,
    w: 9.88,
    h: 0.16,
    fontFace: FONT_MONO,
    fontSize: 8.2,
    color: COLORS.slate,
    margin: 0,
  });
}

function addSvg(slide, svgString, x, y, w, h) {
  const data = svgToDataUri(svgString);
  slide.addImage({ data, ...imageSizingContain(data, x, y, w, h) });
}

function validateSlide(slide, pptx) {
  warnIfSlideHasOverlaps(slide, pptx, {
    muteContainment: true,
    ignoreDecorativeShapes: true,
  });
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

function architectureSvg() {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1280" height="460" viewBox="0 0 1280 460">
      <style>
        .card { fill: #ffffff; stroke: #cbd5e1; stroke-width: 2; rx: 22; ry: 22; }
        .soft { fill: #dff6f2; stroke: #94d5cb; stroke-width: 2; rx: 22; ry: 22; }
        .text { font-family: Lato, Arial, sans-serif; font-size: 24px; font-weight: 700; fill: #111827; }
        .body { font-family: Lato, Arial, sans-serif; font-size: 17px; fill: #334155; }
        .mono { font-family: 'DejaVu Sans Mono', monospace; font-size: 16px; fill: #0f172a; }
        .arrow { stroke: #0f766e; stroke-width: 4; fill: none; stroke-linecap: round; stroke-linejoin: round; }
      </style>
      <rect x="40" y="35" width="1200" height="390" rx="28" ry="28" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <rect class="card" x="80" y="120" width="170" height="86"/>
      <rect class="card" x="310" y="120" width="168" height="86"/>
      <rect class="card" x="538" y="120" width="150" height="86"/>
      <rect class="soft" x="748" y="72" width="176" height="86"/>
      <rect class="soft" x="748" y="205" width="176" height="86"/>
      <rect class="card" x="986" y="120" width="144" height="86"/>
      <rect class="card" x="540" y="310" width="176" height="76"/>
      <rect class="card" x="778" y="310" width="176" height="76"/>
      <rect class="card" x="1016" y="310" width="176" height="76"/>
      <text class="text" x="118" y="171">Frontend</text>
      <text class="body" x="110" y="195">React + Vite</text>
      <text class="mono" x="334" y="171">POST /api/qa</text>
      <text class="text" x="574" y="171">QAService</text>
      <text class="text" x="781" y="123">ClinicalTrials</text>
      <text class="body" x="780" y="148">registry-aware retrieval</text>
      <text class="text" x="802" y="255">PubMed</text>
      <text class="body" x="768" y="280">esearch → esummary → efetch</text>
      <text class="text" x="1025" y="171">Cache</text>
      <text class="body" x="1008" y="195">query / source / embedding</text>
      <text class="text" x="576" y="354">Rerank</text>
      <text class="body" x="566" y="377">bounded evidence selection</text>
      <text class="text" x="819" y="354">LLM Layer</text>
      <text class="body" x="818" y="377">intent + grounded synthesis</text>
      <text class="text" x="1046" y="354">Validation</text>
      <text class="body" x="1045" y="377">citations + final response</text>
      <path class="arrow" d="M250 163 H310"/>
      <path class="arrow" d="M478 163 H538"/>
      <path class="arrow" d="M688 163 H748"/>
      <path class="arrow" d="M688 163 H986"/>
      <path class="arrow" d="M688 163 V248 H748"/>
      <path class="arrow" d="M836 291 V310 H628"/>
      <path class="arrow" d="M1058 206 V248 H658 V310"/>
      <path class="arrow" d="M716 348 H778"/>
      <path class="arrow" d="M954 348 H1016"/>
    </svg>
  `;
}

function lifecycleSvg() {
  const items = [
    "cache",
    "intent",
    "clinical_trials",
    "pubmed",
    "rerank",
    "answer",
    "citation_validation",
    "final_response",
  ];
  const cards = items.map((item, idx) => {
    const x = 38 + idx * 145;
    const fill = idx % 2 === 0 ? "#ffffff" : "#dff6f2";
    return `
      <rect x="${x}" y="68" width="126" height="84" rx="16" ry="16" fill="${fill}" stroke="#cbd5e1" stroke-width="2"/>
      <text x="${x + 12}" y="98" font-family="DejaVu Sans Mono, monospace" font-size="14" fill="#111827">${item}</text>
    `;
  }).join("");
  const arrows = Array.from({ length: items.length - 1 }).map((_, idx) => {
    const x1 = 164 + idx * 145;
    const x2 = 184 + idx * 145;
    return `<path d="M${x1} 110 H${x2}" stroke="#0f766e" stroke-width="4" stroke-linecap="round"/>`;
  }).join("");
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1230" height="250" viewBox="0 0 1230 250">
      <rect x="10" y="18" width="1210" height="214" rx="24" ry="24" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
      ${cards}
      ${arrows}
      <text x="46" y="190" font-family="Lato, Arial, sans-serif" font-size="17" font-weight="700" fill="#111827">Observable by design:</text>
      <text x="222" y="190" font-family="Lato, Arial, sans-serif" font-size="16" fill="#334155">the trace records route, timings, query parameters, selected evidence, and degraded mode reasons.</text>
    </svg>
  `;
}

function pipelineGuardrailSvg() {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1180" height="340" viewBox="0 0 1180 340">
      <style>
        .card { fill: #ffffff; stroke: #cbd5e1; stroke-width: 2; rx: 22; ry: 22; }
        .soft { fill: #dff6f2; stroke: #94d5cb; stroke-width: 2; rx: 22; ry: 22; }
        .warn { fill: #fde7e7; stroke: #f2b8b8; stroke-width: 2; rx: 22; ry: 22; }
        .text { font-family: Lato, Arial, sans-serif; font-size: 22px; font-weight: 700; fill: #111827; }
        .body { font-family: Lato, Arial, sans-serif; font-size: 16px; fill: #334155; }
        .arrow { stroke: #0f766e; stroke-width: 4; fill: none; stroke-linecap: round; stroke-linejoin: round; }
      </style>
      <rect class="card" x="24" y="72" width="220" height="98"/>
      <rect class="soft" x="306" y="72" width="220" height="98"/>
      <rect class="card" x="588" y="72" width="220" height="98"/>
      <rect class="warn" x="870" y="72" width="220" height="98"/>
      <text class="text" x="70" y="114">Normalized snippets</text>
      <text class="body" x="58" y="142">source-aware evidence units</text>
      <text class="text" x="368" y="114">Hybrid rerank</text>
      <text class="body" x="332" y="142">small bounded evidence window</text>
      <text class="text" x="657" y="114">Structured answer</text>
      <text class="body" x="618" y="142">citation_ids, limits, rationale</text>
      <text class="text" x="900" y="114">Validate or fallback</text>
      <text class="body" x="907" y="142">retry or extractive mode</text>
      <path class="arrow" d="M244 121 H306"/>
      <path class="arrow" d="M526 121 H588"/>
      <path class="arrow" d="M808 121 H870"/>
      <rect x="70" y="228" width="1040" height="60" rx="18" ry="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
      <text x="96" y="264" font-family="Lato, Arial, sans-serif" font-size="18" font-weight="700" fill="#111827">Principle:</text>
      <text x="188" y="264" font-family="Lato, Arial, sans-serif" font-size="18" fill="#334155">the model never invents the evidence base; it only organizes retrieved evidence into a conservative answer.</text>
    </svg>
  `;
}

function uiWireframeSvg() {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1240" height="420" viewBox="0 0 1240 420">
      <rect x="20" y="20" width="1200" height="380" rx="28" ry="28" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="56" y="48" width="330" height="86" rx="20" ry="20" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="56" y="154" width="330" height="76" rx="18" ry="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="56" y="248" width="330" height="76" rx="18" ry="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="420" y="48" width="346" height="108" rx="22" ry="22" fill="#dff6f2" stroke="#94d5cb" stroke-width="2"/>
      <rect x="420" y="174" width="346" height="86" rx="22" ry="22" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="420" y="278" width="346" height="92" rx="22" ry="22" fill="#fde7e7" stroke="#f2b8b8" stroke-width="2"/>
      <rect x="800" y="48" width="370" height="146" rx="22" ry="22" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="800" y="214" width="370" height="156" rx="22" ry="22" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
      <text x="88" y="86" font-family="Lato, Arial, sans-serif" font-size="19" font-weight="700" fill="#111827">Question input</text>
      <text x="88" y="110" font-family="Lato, Arial, sans-serif" font-size="15" fill="#334155">toggles + max sources</text>
      <text x="88" y="198" font-family="Lato, Arial, sans-serif" font-size="19" font-weight="700" fill="#111827">Example prompts</text>
      <text x="88" y="292" font-family="Lato, Arial, sans-serif" font-size="19" font-weight="700" fill="#111827">Submit question</text>
      <text x="452" y="90" font-family="Lato, Arial, sans-serif" font-size="21" font-weight="700" fill="#111827">Direct answer</text>
      <text x="452" y="117" font-family="Lato, Arial, sans-serif" font-size="16" fill="#334155">grounded answer block</text>
      <text x="452" y="214" font-family="Lato, Arial, sans-serif" font-size="21" font-weight="700" fill="#111827">Why this answer</text>
      <text x="452" y="240" font-family="Lato, Arial, sans-serif" font-size="16" fill="#334155">supporting bullets from evidence</text>
      <text x="452" y="318" font-family="Lato, Arial, sans-serif" font-size="21" font-weight="700" fill="#111827">Limitations</text>
      <text x="452" y="344" font-family="Lato, Arial, sans-serif" font-size="16" fill="#334155">uncertainty shown separately</text>
      <text x="834" y="92" font-family="Lato, Arial, sans-serif" font-size="21" font-weight="700" fill="#111827">Grouped citations</text>
      <text x="834" y="118" font-family="Lato, Arial, sans-serif" font-size="16" fill="#334155">open source drawer to inspect metadata and snippets</text>
      <text x="834" y="258" font-family="Lato, Arial, sans-serif" font-size="21" font-weight="700" fill="#111827">Pipeline trace</text>
      <text x="834" y="284" font-family="Lato, Arial, sans-serif" font-size="16" fill="#334155">route, cache, timings, stage cards, raw JSON</text>
    </svg>
  `;
}

function demoMatrixSvg() {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="1210" height="330" viewBox="0 0 1210 330">
      <style>
        .h { font-family: Lato, Arial, sans-serif; font-size: 16px; font-weight: 700; }
        .b { font-family: Lato, Arial, sans-serif; font-size: 14px; fill: #334155; }
        .m { font-family: 'DejaVu Sans Mono', monospace; font-size: 13px; fill: #111827; }
      </style>
      <rect x="18" y="18" width="1174" height="294" rx="24" ry="24" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
      <rect x="42" y="42" width="1128" height="40" rx="14" ry="14" fill="#0f766e"/>
      <text class="h" x="62" y="67" fill="#ffffff">Question</text>
      <text class="h" x="724" y="67" fill="#ffffff">Route</text>
      <text class="h" x="826" y="67" fill="#ffffff">Live clicks</text>
      <text class="h" x="1016" y="67" fill="#ffffff">Code anchor</text>
      <rect x="42" y="98" width="1128" height="58" rx="16" ry="16" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <rect x="42" y="170" width="1128" height="58" rx="16" ry="16" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <rect x="42" y="242" width="1128" height="58" rx="16" ry="16" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
      <text class="b" x="60" y="126">Recruiting pembrolizumab trials in metastatic triple-negative breast cancer</text>
      <text class="b" x="60" y="198">Published literature on semaglutide safety in adults with obesity</text>
      <text class="b" x="60" y="270">CAR-T in multiple myeloma: ongoing trials and published evidence</text>
      <text class="m" x="724" y="126">trials</text>
      <text class="m" x="724" y="198">pubmed</text>
      <text class="m" x="724" y="270">blended</text>
      <text class="b" x="826" y="126">citation → source drawer</text>
      <text class="b" x="826" y="198">trace → search term</text>
      <text class="b" x="826" y="270">trace → both retrieval branches</text>
      <text class="m" x="1016" y="126">clinicaltrials.py</text>
      <text class="m" x="1016" y="198">pubmed.py</text>
      <text class="m" x="1016" y="270">qa.py</text>
    </svg>
  `;
}

function buildDeck() {
  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: "QA_WIDE", width: WIDTH, height: HEIGHT });
  pptx.layout = "QA_WIDE";
  pptx.author = "OpenAI Codex";
  pptx.company = "OpenAI";
  pptx.subject = "Clinical QA interview deck from the PPT plus demo runbook";
  pptx.title = "Clinical QA PPT plus demo presentation";
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
      x: 0.72,
      y: 0.64,
      w: 1.14,
      h: 0.08,
      rectRadius: 0.04,
      line: { color: COLORS.teal, transparency: 100 },
      fill: { color: COLORS.teal },
    });
    slide.addText("INTERVIEW WALKTHROUGH", {
      x: 0.78,
      y: 0.82,
      w: 2.7,
      h: 0.2,
      fontFace: FONT_BODY,
      fontSize: 9,
      bold: true,
      color: COLORS.teal,
      charSpace: 1.1,
      margin: 0,
    });
    addFittedText(
      slide,
      "Clinical QA MVP: Grounded Answers over ClinicalTrials.gov and PubMed",
      {
        x: 0.78,
        y: 1.12,
        w: 6.54,
        h: 1.12,
        fontSize: 28,
        minFontSize: 25,
        maxFontSize: 30,
        bold: true,
        color: COLORS.ink,
        leading: 1.04,
      },
      FONT_HEAD
    );
    addFittedText(
      slide,
      "An interview-ready deck for explaining backend architecture, source-aware query design, grounded answers, and tradeoffs through both slides and live code.",
      {
        x: 0.82,
        y: 2.42,
        w: 6.2,
        h: 0.56,
        fontSize: 14,
        minFontSize: 12.5,
        maxFontSize: 14.8,
        color: COLORS.slate,
        leading: 1.22,
      }
    );
    addPill(slide, "30-minute flow", 0.84, 3.16, 1.58, {});
    addPill(slide, "PPT + live demo", 2.56, 3.16, 1.72, {
      fill: COLORS.bluePale,
      line: COLORS.bluePale,
      color: COLORS.blue,
    });
    addPill(slide, "Evidence-first", 4.42, 3.16, 1.64, {
      fill: COLORS.amberPale,
      line: COLORS.amberPale,
      color: COLORS.amber,
    });
    addCard(slide, {
      x: 7.56,
      y: 0.98,
      w: 2.28,
      h: 1.34,
      title: "What it is",
      body: "Single-turn clinical QA with live retrieval, grounded synthesis, and inspectable citations.",
      fill: COLORS.white,
    });
    addCard(slide, {
      x: 10.0,
      y: 0.98,
      w: 2.54,
      h: 1.34,
      title: "What it is not",
      body: "Not a diagnosis engine. The model is not the source of truth.",
      fill: COLORS.white,
      accent: COLORS.red,
      line: "F3C5C5",
    });
    addCard(slide, {
      x: 7.56,
      y: 2.58,
      w: 4.98,
      h: 1.74,
      title: "This talk will answer four questions",
      body: "1. How I would architect the backend\n2. How I query ClinicalTrials.gov and PubMed\n3. How I surface accurate, cited answers\n4. Which tradeoffs I would make and why",
      fill: COLORS.tealPale,
      bodyFontSize: 11.3,
    });
    addCard(slide, {
      x: 0.84,
      y: 4.62,
      w: 11.72,
      h: 1.18,
      title: "Framing line",
      body: "The strongest way to present this project is not as a hypothetical design, but as architecture reasoning backed by a working MVP and concrete code paths.",
      fill: COLORS.white,
      bodyFontSize: 13,
      bodyMin: 12,
      bodyMax: 13.5,
    });
    addCodeStrip(slide, "Show live", "frontend/src/App.tsx");
    addFooter(slide, "Slide 1 · framing and positioning");
    slide.addNotes(`I want to frame this as an implemented MVP, not just a whiteboard architecture exercise.
The system takes a clinical question, retrieves live evidence from ClinicalTrials.gov and PubMed, normalizes and reranks that evidence, and then uses an LLM to produce a grounded answer with citations and a pipeline trace.
So in this walkthrough, I’m going to focus on four things: how I would structure the backend, how I query these two sources differently, how I surface accurate cited answers, and what tradeoffs I made along the way.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Backend",
      title: "How I Would Architect the Backend",
      subtitle: "Thin HTTP layer, one orchestration service, source-specific retrieval services, a provider-neutral LLM layer, and a separate cache layer.",
      page,
    });
    addSvg(slide, architectureSvg(), 0.82, 2.1, 11.7, 2.9);
    addCard(slide, {
      x: 0.84,
      y: 5.28,
      w: 3.56,
      h: 0.94,
      title: "Why split responsibilities",
      body: "Different failure modes: API lifecycle, retrieval logic, ranking, generation, and persistence should not collapse into one service.",
      fill: COLORS.white,
      bodyFontSize: 10.5,
    });
    addCard(slide, {
      x: 4.58,
      y: 5.28,
      w: 3.56,
      h: 0.94,
      title: "What the repo proves",
      body: "The current code already follows this separation through main.py, qa.py, source services, rerank.py, llm_service.py, and cache.py.",
      fill: COLORS.tealPale,
      bodyFontSize: 10.4,
    });
    addCard(slide, {
      x: 8.32,
      y: 5.28,
      w: 4.1,
      h: 0.94,
      title: "What I would emphasize verbally",
      body: "This is not a giant function. It is a pipeline with clear interfaces between retrieval, synthesis, and validation.",
      fill: COLORS.white,
      bodyFontSize: 10.4,
    });
    addCodeStrip(slide, "Show live", "backend/app/main.py · backend/app/services/qa.py");
    addFooter(slide, "Slide 2 · backend architecture");
    slide.addNotes(`If I were designing this backend from scratch, I would separate orchestration from source-specific retrieval logic.
The HTTP layer should stay thin and mostly handle schemas, dependency wiring, and lifecycle concerns.
Then I would have one orchestration service that owns the end-to-end QA flow, separate services for ClinicalTrials.gov and PubMed, a provider-neutral LLM layer, and a separate cache layer.
The reason is that these are different responsibilities with different failure modes.
And that is basically how this repo is structured today. It is not one giant function. Retrieval, reranking, generation, validation, and caching are split into separate modules.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "API",
      title: "API Design and Request Lifecycle",
      subtitle: "Keep the API simple, separate source drill-down, and make the end-to-end pipeline observable.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.06,
      w: 3.18,
      h: 3.96,
      title: "Public endpoints",
      body: "POST /api/qa\nMain answer endpoint with question, filters, and evidence budget\n\nGET /api/sources/{source_type}/{source_id}\nInspect the cited source in local cache\n\nGET /api/health\nExpose operational readiness, not just liveness",
      fill: COLORS.white,
      bodyFontSize: 11,
    });
    addSvg(slide, lifecycleSvg(), 4.24, 2.12, 8.2, 1.68);
    addCard(slide, {
      x: 4.24,
      y: 4.04,
      w: 4.0,
      h: 1.98,
      title: "Design principle",
      body: "The main response should stay compact and useful, while evidence drill-down and operational state live in dedicated endpoints.",
      fill: COLORS.tealPale,
      bodyFontSize: 11.2,
    });
    addCard(slide, {
      x: 8.46,
      y: 4.04,
      w: 3.98,
      h: 1.98,
      title: "Why observability matters",
      body: "In clinical QA, you do not only want an answer. You want to know whether the answer came from routing, retrieval, ranking, generation, or fallback behavior.",
      fill: COLORS.white,
      bodyFontSize: 11,
    });
    addCodeStrip(slide, "Show live", "backend/app/main.py · backend/app/services/qa.py");
    addFooter(slide, "Slide 3 · API design and lifecycle");
    slide.addNotes(`On the API side, I would keep the main question-answering endpoint very simple.
It should take the question, a small set of filters, and an evidence budget like max sources.
Then I would separate source detail into a dedicated endpoint, because citation drill-down is important, but I do not want to overload the main response.
I also like having a real health endpoint, not just a ping endpoint, so I can expose provider readiness and cache state.
The other important design choice here is observability. In clinical QA, it is not enough to return an answer. You also need to understand why the system answered that way.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "ClinicalTrials.gov",
      title: "How I Structure Queries Against ClinicalTrials.gov",
      subtitle: "Treat the trial registry as a structured source, not as generic keyword search.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.06,
      w: 3.62,
      h: 3.94,
      title: "Query planning",
      body: "Use registry-aware fields first:\nquery.cond\nquery.intr\nquery.term fallback\n\nTranslate the question into condition, intervention, and status intent instead of passing the raw sentence.",
      fill: COLORS.white,
      bodyFontSize: 11.2,
    });
    addCard(slide, {
      x: 4.66,
      y: 2.06,
      w: 3.62,
      h: 3.94,
      title: "Status-aware behavior",
      body: "Recruiting and ongoing questions should influence retrieval planning early.\n\nThat means filtering during retrieval, not only after truncation.\n\nThis is where a lot of subtle false negatives come from.",
      fill: COLORS.tealPale,
      bodyFontSize: 11.2,
    });
    addCard(slide, {
      x: 8.48,
      y: 2.06,
      w: 3.96,
      h: 1.78,
      title: "Normalized snippet types",
      body: "status\nsummary\neligibility\noutcomes",
      fill: COLORS.white,
      bodyFontSize: 12,
    });
    addCard(slide, {
      x: 8.48,
      y: 4.02,
      w: 3.96,
      h: 1.98,
      title: "Concrete bug worth mentioning",
      body: "If you retrieve only a few studies first and filter for recruiting afterward, you can miss the real recruiting matches. I fixed that exact issue in this repo.",
      fill: COLORS.rosePale,
      accent: COLORS.red,
      line: "F3C5C5",
      bodyFontSize: 10.8,
    });
    addCodeStrip(slide, "Show live", "backend/app/services/clinicaltrials.py");
    addFooter(slide, "Slide 4 · ClinicalTrials query design");
    slide.addNotes(`For ClinicalTrials.gov, I would not treat it like a generic search engine.
I would translate the question into trial-registry semantics, especially condition, intervention, and status intent.
So instead of sending the raw sentence, I try to populate fields like query.cond and query.intr, and I only fall back to a looser query.term when needed.
Status-aware planning is especially important. A recruiting-trials question is really a structured filtering problem, not just a keyword problem.
In fact, one real bug I fixed in this repo was exactly in this area. If you retrieve too few trials first and filter for recruiting afterward, you can miss the true recruiting matches.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "PubMed",
      title: "How I Structure Queries Against PubMed",
      subtitle: "PubMed is a different retrieval problem, so it gets a different query model and a different normalization path.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.06,
      w: 3.74,
      h: 3.94,
      title: "Three-step path",
      body: "1. esearch\nFind candidate PMIDs\n\n2. esummary\nPull article metadata\n\n3. efetch\nGet abstracts and turn them into sentence-level evidence chunks",
      fill: COLORS.white,
      bodyFontSize: 11.3,
    });
    addCard(slide, {
      x: 4.78,
      y: 2.06,
      w: 3.6,
      h: 3.94,
      title: "Query inputs",
      body: "condition\nintervention\npopulation\noutcome intent\n\nThese become conservative Title or Abstract clauses rather than one loose full-sentence search.",
      fill: COLORS.bluePale,
      accent: COLORS.blue,
      bodyFontSize: 11.1,
    });
    addCard(slide, {
      x: 8.58,
      y: 2.06,
      w: 3.84,
      h: 1.78,
      title: "Normalized snippet types",
      body: "title\nmetadata\nabstract_1 ... abstract_n",
      fill: COLORS.white,
      bodyFontSize: 12,
    });
    addCard(slide, {
      x: 8.58,
      y: 4.02,
      w: 3.84,
      h: 1.98,
      title: "Limitation I would state clearly",
      body: "This MVP is mostly abstract-grounded, not full-text-grounded. I would rather be precise about evidence depth than imply more than the system actually has.",
      fill: COLORS.amberPale,
      accent: COLORS.amber,
      line: COLORS.amberPale,
      bodyFontSize: 10.7,
    });
    addCodeStrip(slide, "Show live", "backend/app/services/pubmed.py");
    addFooter(slide, "Slide 5 · PubMed query design");
    slide.addNotes(`PubMed is a very different retrieval problem, so I would not force it into the same abstraction as trial registry search.
Here I build a PubMed-style query from condition, intervention, population, and outcome intent, and I express that mostly as Title and Abstract clauses.
Then I use a three-step path: esearch to get candidate PMIDs, esummary for metadata, and efetch for abstract text.
That gives me a lightweight but reliable literature pipeline.
The limitation I would state very clearly is that this MVP is mostly abstract-grounded, not full-text-grounded. I think being explicit about that is better than overstating the depth of evidence.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Grounding",
      title: "How I Surface Accurate, Cited Answers",
      subtitle: "Bound the evidence first, then constrain generation, then validate citations before returning the final answer.",
      page,
    });
    addSvg(slide, pipelineGuardrailSvg(), 0.92, 2.04, 11.5, 2.6);
    addCard(slide, {
      x: 0.92,
      y: 4.98,
      w: 3.5,
      h: 1.12,
      title: "Evidence first",
      body: "The evidence window is selected before generation, not after generation.",
      fill: COLORS.white,
      bodyFontSize: 10.6,
    });
    addCard(slide, {
      x: 4.62,
      y: 4.98,
      w: 3.5,
      h: 1.12,
      title: "Structured outputs",
      body: "The model returns a schema with citation IDs instead of unconstrained prose.",
      fill: COLORS.tealPale,
      bodyFontSize: 10.6,
    });
    addCard(slide, {
      x: 8.32,
      y: 4.98,
      w: 4.0,
      h: 1.12,
      title: "Safety net",
      body: "If citation support is weak, retry once and then fall back to a conservative extractive answer.",
      fill: COLORS.rosePale,
      accent: COLORS.red,
      line: "F3C5C5",
      bodyFontSize: 10.6,
    });
    addCodeStrip(slide, "Show live", "backend/app/services/rerank.py · llm_service.py · qa.py");
    addFooter(slide, "Slide 6 · accurate, cited answers");
    slide.addNotes(`My approach is not to trust the model first and ask for citations later.
I do the opposite. I first build a bounded evidence window, and then I ask the model to synthesize only from that evidence.
In this repo, the evidence is normalized into snippets, reranked, and then passed into a structured answer step rather than a free-form generation step.
The model has to return citation IDs, and those citation IDs are validated against the retrieved snippets.
If the citations do not validate, the system retries, and if support is still weak, it falls back to a conservative extractive answer.
That fallback matters, because in a clinical setting, a conservative supported answer is usually better than a polished but unsupported one.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Trust",
      title: "Why the UI Matters for Trust",
      subtitle: "Trust is not only about backend accuracy. It is also about how you expose evidence, limitations, and system behavior.",
      page,
    });
    addSvg(slide, uiWireframeSvg(), 0.82, 2.02, 11.72, 2.84);
    addCard(slide, {
      x: 0.92,
      y: 5.02,
      w: 3.72,
      h: 1.1,
      title: "Separate uncertainty",
      body: "Limitations deserve their own block instead of being buried in answer prose.",
      fill: COLORS.white,
      bodyFontSize: 10.6,
    });
    addCard(slide, {
      x: 4.84,
      y: 5.02,
      w: 3.72,
      h: 1.1,
      title: "Inspectable citations",
      body: "Source drawer exposes metadata plus all available snippets behind a cited source.",
      fill: COLORS.tealPale,
      bodyFontSize: 10.6,
    });
    addCard(slide, {
      x: 8.76,
      y: 5.02,
      w: 3.66,
      h: 1.1,
      title: "Not a black box",
      body: "The pipeline trace shows route, cache, timings, stage cards, and raw JSON.",
      fill: COLORS.white,
      bodyFontSize: 10.6,
    });
    addCodeStrip(slide, "Show live", "frontend/src/App.tsx · source drawer · trace drawer");
    addFooter(slide, "Slide 7 · UI and inspectability");
    slide.addNotes(`For me, trust is not only a backend problem. It is also a presentation problem.
I want the user to see the direct answer, the supporting evidence, the limitations, and the citations as separate things.
That is why the UI has a dedicated limitations section instead of hiding uncertainty inside one answer paragraph.
I also do not treat citations as simple links. The source drawer lets the user inspect cached metadata and the available snippets behind each citation.
And the pipeline trace makes the system less of a black box, which I think is especially important for medical or clinical use cases.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Tradeoffs",
      title: "Tradeoffs and Design Decisions",
      subtitle: "Prefer the simplest design that solves the right risk first: routing, grounding, citation validity, and debuggability.",
      page,
    });
    addCard(slide, {
      x: 0.84,
      y: 2.08,
      w: 5.56,
      h: 4.08,
      title: "What I chose",
      body: "live retrieval + SQLite cache\nbounded reranking instead of a vector database\nprovider-neutral OpenAI or vLLM layer\nabstract-grounded PubMed baseline\nsingle-turn UX",
      fill: COLORS.white,
      bodyFontSize: 11.3,
    });
    addCard(slide, {
      x: 6.62,
      y: 2.08,
      w: 5.56,
      h: 4.08,
      title: "Why I chose it",
      body: "faster to build and easier to debug\nhigher early risk is wrong routing and weak grounding, not missing infrastructure\ncheaper and easier to demo locally\nhonest evidence depth\nbetter trust and inspectability",
      fill: COLORS.tealPale,
      bodyFontSize: 11.3,
    });
    addCodeStrip(slide, "Show live", "backend/app/services/cache.py · backend/app/services/llm_service.py");
    addFooter(slide, "Slide 8 · tradeoffs");
    slide.addNotes(`If this were just an interview question, I would not give the easy answer of saying I would immediately add offline ingestion, a vector database, full-text pipelines, and an agent framework.
I think the stronger answer is knowing what to add later and what not to add too early.
For this MVP, I deliberately prioritized source-aware retrieval, grounded synthesis, citation validity, and debuggability over infrastructure complexity.
So the main tradeoff is simplicity versus scale.
I chose the simpler design because the early risk in clinical QA is usually not lack of infrastructure. It is wrong routing, weak grounding, and poor transparency.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Live Demo",
      title: "What I Would Show Live During the Interview",
      subtitle: "Keep the demo simple: one question, one citation drill-down, one trace drill-down, then map that behavior back to the code.",
      page,
    });
    addSvg(slide, demoMatrixSvg(), 0.9, 2.0, 11.5, 2.75);
    addCard(slide, {
      x: 0.92,
      y: 5.02,
      w: 3.74,
      h: 1.08,
      title: "Best first click",
      body: "Start with a trials question. It makes route choice and registry semantics easiest to explain.",
      fill: COLORS.white,
      bodyFontSize: 10.5,
    });
    addCard(slide, {
      x: 4.88,
      y: 5.02,
      w: 3.74,
      h: 1.08,
      title: "Best second click",
      body: "Open a citation and show that the UI can inspect the underlying source instead of only showing a hyperlink.",
      fill: COLORS.tealPale,
      bodyFontSize: 10.5,
    });
    addCard(slide, {
      x: 8.84,
      y: 5.02,
      w: 3.56,
      h: 1.08,
      title: "Best third click",
      body: "Open the trace and connect the visible stages back to the backend pipeline.",
      fill: COLORS.white,
      bodyFontSize: 10.5,
    });
    addCodeStrip(slide, "Show live", "frontend/src/App.tsx · qa.py · clinicaltrials.py · pubmed.py");
    addFooter(slide, "Slide 9 · demo flow");
    slide.addNotes(`I would keep the live demo very simple.
I would start with a trials-first question, because it makes route choice and structured registry retrieval easiest to explain.
Then I would click into a citation and open the source drawer, so the audience can see that the system exposes the evidence behind the answer.
After that, I would open the pipeline trace and connect what the UI shows back to the backend stages.
That is usually enough. I would avoid jumping around too many files or trying to demo every possible mode.`);
    validateSlide(slide, pptx);
    page += 1;
  }

  {
    const slide = pptx.addSlide();
    addTitleBlock(slide, {
      kicker: "Closing",
      title: "If I Had Another Week",
      subtitle: "The next gains would come from better indexing, layered evaluation, and stronger planning for blended questions.",
      page,
    });
    addCard(slide, {
      x: 0.92,
      y: 2.12,
      w: 3.62,
      h: 3.88,
      title: "1. Stronger offline indexing",
      body: "Improve latency, recall, and observability once the retrieval logic itself is stable enough to deserve heavier infrastructure.",
      fill: COLORS.white,
      bodyFontSize: 11.1,
    });
    addCard(slide, {
      x: 4.86,
      y: 2.12,
      w: 3.62,
      h: 3.88,
      title: "2. Layered evaluation",
      body: "Evaluate route quality, source retrieval, snippet relevance, citation validity, and final answer usefulness separately instead of using only one end metric.",
      fill: COLORS.tealPale,
      bodyFontSize: 11.05,
    });
    addCard(slide, {
      x: 8.8,
      y: 2.12,
      w: 3.62,
      h: 3.88,
      title: "3. Better blended planning",
      body: "The hardest open problem is not a single-source question. It is balancing trial evidence and published literature in one coherent answer.",
      fill: COLORS.white,
      bodyFontSize: 11.05,
    });
    slide.addShape("roundRect", {
      x: 0.92,
      y: 6.22,
      w: 11.48,
      h: 0.56,
      rectRadius: 0.16,
      line: { color: COLORS.tealDark, transparency: 100 },
      fill: { color: COLORS.tealDark },
    });
    addFittedText(
      slide,
      "The model is not the source of truth. The retrieved evidence is.",
      {
        x: 1.2,
        y: 6.39,
        w: 10.94,
        h: 0.18,
        fontSize: 13,
        minFontSize: 12,
        maxFontSize: 13.6,
        color: COLORS.white,
        bold: true,
        align: "center",
      },
      FONT_HEAD
    );
    addFooter(slide, "Slide 10 · next steps and closing");
    slide.addNotes(`If I had another week, I would not spend it polishing the UI first.
I would focus on three things.
First, stronger offline indexing to improve latency, recall, and observability.
Second, layered evaluation, so I am not only judging the final answer, but also route quality, retrieval quality, snippet relevance, and citation validity.
Third, better planning for blended questions, because the hardest case right now is not a single-source question. It is synthesizing trial evidence and published literature together in a balanced way.

If I had to summarize the design in one sentence, it would be this: the model is not the source of truth, the retrieved evidence is.
So most of my design decisions are really about making retrieval more source-aware, keeping the evidence window bounded, validating citations, and making the whole system inspectable.
That is the bar I would want for any clinical QA product, even at the MVP stage.`);
    validateSlide(slide, pptx);
  }

  return pptx;
}

async function main() {
  const outDir = path.join(__dirname, "dist");
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, "clinical_qa_ppt_plus_demo_presentation.pptx");
  const pptx = buildDeck();
  await pptx.writeFile({ fileName: outPath, compression: true });
  console.log(`Wrote ${outPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
