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
- **`@preact/signals`** — reactive state management (used in Config Hub).
- **Hooks & Context** — state management patterns (used in Bot Webapp).
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

## Stack-Based Navigation (SPA)

The Telegram Web App is a Single Page Application that avoids standard client-side router packages (like React Router) to prevent conflicts with Telegram's native view dynamics (such as `MainButton` overlays and keyboard height adjustments).

It uses a custom CSS-transform-based stack navigator managed via `useNavigator()`:
- **Push**: Renders the new screen offscreen and slides it in from the right (`translateX(100%) -> translateX(0)`), matching native iOS/Telegram aesthetics.
- **Pop**: Slides the active screen out to the right, using a **delayed unmount** pattern. The exiting screen remains in the DOM until the `300ms` slide-out transition finishes. This prevents cleanup triggers (like physical `BackButton.hide()` or `MainButton.hide()`) from firing prematurely mid-animation.
- **Unified Screens**: Detail pages (like `BuildDetailScreen.tsx`) handle multiple build states (active building, success, failure) within a single component. On build completion, they transition in-place without loading flashes by retaining the last-known active state until the final result is fetched.

---

## Native Integration Hooks

Telegram SDK integrations are encapsulated in native-first, declarative React hooks rather than dispersed imperative calls:

- **`useMainButton(config, isActive)`** — Manages the native `tg.MainButton` lifecycle (text, color, disabled state, loading spinner, and click handler swaps).
  - *Singleton Contention Resolution*: When multiple screens are mounted, only the topmost active screen (`isActive = true`) controls the singleton `MainButton`. Inactive hooks yield control and reset the button.
  - *Automatic Cleanup*: Ensures `MainButton` is hidden, progress spinners are stopped, and callbacks are unregistered when the component unmounts.
- **`useCloudStorage(key, fallback)`** — Provides reactive read/write access to `tg.CloudStorage` (wrapping the callback-based API with Promises) and falls back to `localStorage` in browser preview mode. Used to persist preferences like "Notify on completion".

---

## Telegram Design Language

Both frontends follow Telegram's design patterns (per `custom-rule.md`). The bot webapp integrates with `window.Telegram.WebApp` for theming, haptic feedback, and back-button handling. The emulator mode (`emulator.ts`) provides a browser-based preview for development without Telegram. It features fully-implemented floating controls for the `MainButton`/`BackButton` as well as light/dark auto-syncing theme params.

---

## Native-First Principle

Whenever interacting with the user or OS inside a Telegram Mini App, you MUST prioritize native `window.Telegram.WebApp` APIs over web wrappers:
- **Alerts/Dialogs**: Never use `window.alert`, `window.confirm`, or custom HTML modal dialogs for basic prompts. Use `tg.showAlert()`, `tg.showConfirm()`, and `tg.showPopup()`.
- **Storage**: Never use `localStorage` for cross-device persistence. Use `tg.CloudStorage` or `tg.DeviceStorage`.
- **Buttons**: Use `tg.MainButton` and `tg.SecondaryButton` for primary actions instead of sticky HTML footers.
- **Iconography**: Avoid text emojis (`✅`, `❌`). Use clean, monocolor vector icons (`lucide-preact`) to match Telegram's native aesthetic.

---

## Testing

For the frontend testing methodology — Vitest setup, component testing, Telegram SDK mocking, and hook testing patterns — see `testing-conventions.md`.
