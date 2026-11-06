# TVO Chameleon client

React + Vite + TypeScript frontend for reviewing accessibility suggestions on a TVO Learn page.

Pages come from the capture server (`server.js` in the repository root). Suggestions for captured pages come from the analysis backend (`backend/` in the repository root), which the client reaches through the capture server's `/backend` forwarding. The backend fills the Dyslexia version. The General version has no analysis yet, so it is empty for captured pages. If the backend is not running, the page still opens and the Dyslexia version says why there is no analysis.

The stand-in `public/sample-page.html` does not use the backend. Its Dyslexia version uses copies of the backend team's sample outputs in `src/infrastructure/samples/`, and its General version uses placeholders. Decisions are kept in this browser's `localStorage` for all pages.

## Run it

```
cd client
npm install
npm run dev
```

Open http://localhost:5173. The sample page works on its own.

To capture real pages, also run the capture server on port 3000, from the repository root:

```
npm install
npx playwright install chromium
npm start
```

The dev server forwards `/api`, `/snapshots` and `/backend` to it. A capture can take a few minutes.

To get suggestions for captured pages, also start the analysis backend on port 8001, from the repository root (the capture server forwards `/backend` there; set `BACKEND_URL` to change it):

```
cd backend
uv sync
uv run python -m nltk.downloader cmudict    # first run only
MODEL_MOCK=1 uv run uvicorn main:app --port 8001
```

`MODEL_MOCK=1` returns the same fixed text suggestions for every page. See the repository README for using a real model.

To run everything from one address, build the client (`npm run build:client` in the repository root) and open http://localhost:3000: the capture server then serves the client too.

## Scripts

| Command                | What it does                                   |
| ---------------------- | ---------------------------------------------- |
| `npm run dev`          | Dev server with hot reload                     |
| `npm run typecheck`    | TypeScript check (strict mode)                 |
| `npm test`             | Run the tests (Vitest, with jsdom for the DOM) |
| `npm run build`        | Type check, then production build into `dist/` |
| `npm run preview`      | Serve the production build locally             |
| `npm run format`       | Format the code with Prettier                  |
| `npm run format:check` | Check formatting without changing files        |

## Structure

```
src/
  main.tsx          mounts the app
  App.tsx           chooses the data sources and starts the UI
  styles.css        global styles
  domain/           review and capture types and rules (plain TypeScript)
  application/      the interfaces for data sources, and the hooks that use them
  infrastructure/   the capture server and analysis backend clients, the sample data and the localStorage repository
  ui/               React components and the code that patches the previewed page
public/
  sample-page.html  stand-in for a captured page
```

Dependencies point inward: `ui` and `infrastructure` use `application` and `domain`, and `domain` uses nothing else.

## How the backend is connected

`src/App.tsx` builds the repository from `createAnalysisReviewRepository` (`src/infrastructure/analysisReviewRepository.ts`), which wraps the local sample repository. For a captured page it:

1. Loads the page and finds the lesson frame (`frames/f0.html` and so on). The lesson is what gets analysed, or the page itself when it has no lesson frame.
2. Sends that HTML to `POST /backend/analyze` through `createHttpAnalysisGateway` (`src/infrastructure/httpAnalysisGateway.ts`).
3. For each page-wide rule (font, spacing, colour, layout, emphasis), asks `POST /backend/adapted` for the CSS it would inject, and previews the rule with that CSS.
4. Turns the recommendations into suggestions (`src/infrastructure/recommendationSuggestions.ts`), matching the backend's block ids to elements with `src/infrastructure/pageBlocks.ts`. Recommendations that cannot be shown on the page are left out, such as icon-font tags reported as italics, or mock-model text that is not in the page.

If the model step fails, the rule-based findings are still shown with a note. If the whole analysis fails, the version is empty and the note gives the reason.

Things to keep in mind when changing this:

- The backend and `indexBlocks` must read the exact same HTML string (`normalizeHtml`), or block ids will not line up.
- Patches are applied inside the lesson frame (`targetFrame` in `src/ui/PagePreview.tsx`), so suggestions for captured pages change the lesson content.
- The page must be on the client's origin so patches can be applied. In development the proxy in `vite.config.ts` does this. A production deployment must serve the client and the snapshots from one origin, as `npm start` with a built client does.
- Accept/deny/edit decisions stay in the client (`localStorage`). The backend is stateless.
