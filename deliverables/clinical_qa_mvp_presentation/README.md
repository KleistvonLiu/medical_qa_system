# Clinical QA MVP Presentation

This folder contains an editable PowerPoint deck for a `25-30 minute` walkthrough of the implemented Clinical QA MVP in this repo.

## Artifacts

- `clinical_qa_mvp_presentation.pptx`
  Final PowerPoint deck.
- `clinical_qa_mvp_presentation.js`
  Source file that generates the deck with `PptxGenJS`.
- `pptxgenjs_helpers/`
  Local slide helper bundle required by the source file.
- `package.json` and `package-lock.json`
  Node manifest for rebuilding the deck.

## Rebuild

From this folder:

```bash
npm install
npm run build
```

The build writes the `.pptx` into `dist/`.

## Notes

- The deck is based on the current project implementation plus the narrative in:
  - `../clinical_qa_slides_outline.md`
  - `../clinical_qa_video_script_en_zh.md`
  - `../clinical_qa_request_flow.md`
  - `../clinical_qa_interviewer_qa.md`
- The chosen fonts are `Lato` and `DejaVu Sans Mono`, which are installed on this machine.
- Full PNG rendering and LibreOffice-based font/export validation were not available in this environment because the local machine is missing `pdf2image`, `python-pptx`, and LibreOffice.
