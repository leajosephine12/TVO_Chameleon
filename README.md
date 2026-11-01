# TVO_Chameleon
Group 4 repo for FTL 2026

## Running the app

The capture server (`server.js`) pulls a TVO Learn page into a static copy, and the client (`client/`)
shows that copy next to the review panel.

```
npm install
npx playwright install chromium
npm run build:client
npm start
```

Then open http://localhost:3000, paste a TVO Learn link and press "Capture page". A capture can take a few minutes.

For client development, run `npm start` in the repository root and `npm run dev` in `client/`
(http://localhost:5173 forwards `/api` and `/snapshots` to the server). See `client/README.md`.
