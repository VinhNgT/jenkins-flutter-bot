---
trigger: glob
description: Frontend conventions for Preact + Vite web applications — project structure, state management, build pipeline.
globs: **/frontend/**/*.tsx, **/frontend/**/*.ts, **/frontend/vite.config.*, **/frontend/package.json
---

# Web Conventions

Triggered when editing frontend TypeScript/TSX files. Covers the Preact + Vite stack, project structure, state management, and build pipeline used by both web frontends.

---

## Frontend Stack

- **Preact 10** — lightweight React alternative. No React — this is a pure Preact codebase.
- **`@preact/signals`** — reactive state management. The sole state primitive — no Redux, no stores.
- **Vite 6** — build tool and dev server with HMR.
- **TypeScript** — type safety for all frontend code.
- **`lucide-preact`** — icon library.

---

## Two Frontends, One Stack

Both frontends share identical dependencies, tooling, and project structure:

| Frontend | Location | Serves | Base Path |
|----------|----------|--------|-----------|
| Config Hub Dashboard | `apps/config-hub/frontend/` | Admin web dashboard | `/static/` |
| Telegram Web App | `apps/tg-jenkins-bot/frontend/` | Telegram Mini App | `/webapp/` |

Changes to shared patterns should be applied to both.

---

## Project Structure

Each frontend follows the same layout:

```
frontend/
├── src/
│   ├── main.tsx          # Entry point, renders App
│   ├── App.tsx           # Root component
│   ├── api.ts            # HTTP client functions
│   ├── types.ts          # TypeScript interfaces
│   ├── components/       # Preact functional components
│   ├── context/          # Preact context providers
│   ├── hooks/            # Custom hooks (useSSE, etc.)
│   └── styles/           # CSS files
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

The bot webapp additionally has `emulator.ts` for browser-based Telegram WebApp preview, and `telegram.d.ts` for `window.Telegram.WebApp` type declarations.

---

## Build & Deploy Pipeline

Vite builds directly into the Python service's static directory (`outDir` in `vite.config.ts`):

- **Config Hub** → `src/config_hub/static/` (served at `/static/`)
- **Bot Webapp** → `src/tg_jenkins_bot/webapp/` (served at `/webapp/`)

The Python FastAPI service mounts these as `StaticFiles`. No separate static file server. Content-hashed filenames provide cache-busting; the entry HTML revalidates (`no-cache`), sub-resources are cached aggressively.

Build command: `npm run build` (runs `tsc --noEmit && vite build`).

---

## Dev Proxy

Each Vite dev server proxies API calls to the local Python service:

- Config Hub: `/api` → `http://localhost:9000`
- Bot Webapp: `/api/webapp` → `http://localhost:9090`

---

## SSE Hooks

Real-time data uses custom `useSSE()` hooks that manage `EventSource` lifecycle, reconnection, and typed event parsing. Both frontends implement their own version tailored to their data model.

---

## Telegram Design Language

Both frontends follow Telegram's design patterns (per `custom-rule.md`). The bot webapp integrates with `window.Telegram.WebApp` for theming, haptic feedback, and back-button handling. The emulator mode (`emulator.ts`) provides a browser-based preview for development without Telegram.
