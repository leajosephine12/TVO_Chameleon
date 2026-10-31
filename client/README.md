# TVO Chameleon client

React + Vite + TypeScript frontend for reviewing accessibility suggestions on a TVO Learn page.

Pages come from the capture server (`server.js` on the `PullingTVOWebsitesDraftVersion` branch). Suggestions do not come from a backend yet: only the stand-in `public/sample-page.html` has suggestions, and captured pages show an empty review panel. Its Dyslexia version uses copies of the backend team's sample outputs in `src/infrastructure/samples/`, and its General version uses placeholders. Decisions are kept in this browser's `localStorage`.

## Run it

```
cd client
npm install
npm run dev
```

Open http://localhost:5173. The sample page works on its own.

To capture real pages, also run the capture server on port 3000. In a checkout that has `server.js`:

```
npm install
npx playwright install chromium
npm start
```

The dev server forwards `/api` and `/snapshots` to it. A capture can take a few minutes.

## Scripts

| Command                | What it does                                   |
| ---------------------- | ---------------------------------------------- |
| `npm run dev`          | Dev server with hot reload                     |
| `npm run typecheck`    | TypeScript check (strict mode)                 |
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
  infrastructure/   the capture server client, the sample data and the localStorage repository
  ui/               React components and the code that patches the previewed page
public/
  sample-page.html  stand-in for a captured page
```

Dependencies point inward: `ui` and `infrastructure` use `application` and `domain`, and `domain` uses nothing else.

## Connecting the analysis backend

Implement `ReviewRepository` from `src/application/ports.ts` against the API, then swap the repository created in `src/App.tsx`. `loadSession` receives the page being reviewed. The UI does not need to change, with these limits:

- Each suggestion's `patches` and `targetSelector` must match that page. Captured elements have a `data-cid` attribute, listed in the capture's `elements.json`, which makes a stable selector such as `[data-cid="c12"]`.
- Patches currently reach only the top-level page, not the embedded frames in `frames/`. On real pages much of the lesson lives in those frames, so `applyPatches` must be extended before suggestions can change that content.
- The page must be on the client's origin so patches can be applied. In development the proxy in `vite.config.ts` does this. A production deployment must serve the client and the snapshots from one origin.
