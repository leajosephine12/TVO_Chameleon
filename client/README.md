# TVO Chameleon client

React + Vite + TypeScript frontend. Right now it is a bare starting point: one page that says "TVO Chameleon".

## Run it

```
cd client
npm install
npm run dev
```

Open http://localhost:5173.

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
  main.tsx     mounts the app
  App.tsx      the root component
  styles.css   global styles
```
