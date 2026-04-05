# Clinical QA PPT Plus Demo Presentation

This folder contains an editable PowerPoint deck generated from [clinical_qa_ppt_plus_demo_runbook.md](/home/kleist/Documents/Code/medical_QA_system/deliverables/clinical_qa_ppt_plus_demo_runbook.md).

## Artifacts

- `clinical_qa_ppt_plus_demo_presentation.pptx`
  Final PowerPoint deck.
- `clinical_qa_ppt_plus_demo_presentation.js`
  PptxGenJS source used to generate the deck.
- `pptxgenjs_helpers/`
  Local helper bundle required by the source file.
- `package.json` and `package-lock.json`
  Rebuild manifest.

## What Is In The Deck

- `10` slides
- `10` speaker-notes pages
- Interview-focused flow:
  - framing
  - backend architecture
  - API design and lifecycle
  - ClinicalTrials query design
  - PubMed query design
  - accurate cited answers
  - UI and trust
  - tradeoffs
  - live demo anchors
  - next steps and closing

## Rebuild

From this folder:

```bash
npm install
npm run build
```

The build writes the generated `.pptx` to `dist/`.

## Validation Notes

Authoring-time overlap and out-of-bounds checks in the JavaScript source pass cleanly.

The bundled Python validation tools could not complete in this environment because the local machine is missing:

- `pdf2image`
- `python-pptx`
- LibreOffice / `soffice`

So PNG rendering, overflow rendering checks, and LibreOffice-based font validation were attempted but blocked by missing local dependencies.
