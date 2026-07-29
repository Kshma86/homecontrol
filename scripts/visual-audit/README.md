# HomeControl Visual Audit

Dev-only screenshot helper for the UI v2 rollout.

## Setup

```bash
npm install --prefix scripts/visual-audit
npx --prefix scripts/visual-audit playwright install chromium
```

## Start The Local Capture Server

```bash
npm run --prefix scripts/visual-audit server
```

The UI calls `http://<current-host>:5015/capture` when the V2 Preview screenshot button is pressed.
Screenshots are saved under:

```text
visual-audit/runs/YYYY-MM-DD/<tab>/<time>-<viewport>.png
```

## Single CLI Capture

```bash
npm run --prefix scripts/visual-audit capture -- '{"tab":"power-wall","width":1440,"height":900,"url":"http://127.0.0.1:3000/#power-wall","uiV2Tabs":{"power-wall":true}}'
```
