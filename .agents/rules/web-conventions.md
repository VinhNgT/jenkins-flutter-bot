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
- **Hooks & Context** — state management for both frontends.
- **Vite 6** — build tool and dev server with HMR.
- **TypeScript** — type safety for all frontend code.
- **`lucide-preact`** — icon library.

---

## Shared Workspace Libraries

To maintain absolute styling parity, prevent code drift, and optimize component reuse, all frontend projects must consume shared Preact/TypeScript core packages located under `libs/`:

- **`libs/platform-core`**: Provides unified cross-platform contexts/providers:
  - `PlatformContext`: Determines the active environment and configuration injection.
  - `PlatformStorageContext`: Implements a standard storage interface (Promise-based `getItem`/`setItem`) automatically mapping to Telegram `CloudStorage` (when in the Mini App) or standard `localStorage` (when in browser).
  - `PrimaryButtonContext`: Standardizes the declarative hook `usePrimaryButton` for setting primary screen CTA buttons.
- **`libs/tg-core-preact`**: Handles native Telegram SDK bindings:
  - `TelegramContext`: Initializes and injects the raw `window.Telegram.WebApp` SDK.
  - `useTheme` / `useViewport`: Reactive hooks syncing theme colors (`--tg-color-*` variables) and viewport sizes to Preact lifecycle.
- **`libs/tg-ui-preact`**: A high-fidelity, unified Telegram UI library. 
  - Exposes reusable Preact components designed specifically for Telegram's aesthetics: `Badge`, `Button`, `Dialog`, `ErrorBoundary`, `Input`, `List`, `ListItem`, `Navigator`, `Scaffold`, `Shimmer` (skeleton loaders), `Spinner`, `Switch`, `TextArea`, `Toast`.
  - Imports all styling from the shared `src/styles/telegram.css` stylesheet.
  - **Independence Constraint**: Must remain fully independent and MUST NOT import or depend on other workspace libraries (such as `platform-core` or `tg-core-preact`), keeping it a pure, lightweight, reusable component-only library.

> [!IMPORTANT]
> **Component Reusability Rule:** Developers must NEVER build duplicate UI controls (like switches, standard lists, inputs, or headers) or make raw, imperative calls to the Telegram SDK inside the webapps. All custom views must utilize the declarative components and hooks provided in the shared packages.

---

## Two Frontends, One Stack

Both frontends share identical dependencies, tooling, project structure, and design system:

| Frontend | Location | Serves | Base Path |
|----------|----------|--------|-----------|
| Config Hub Mini App | `apps/config-hub/frontend/` | Admin Telegram Mini App | `/webapp-admin/` |
| Telegram Web App | `apps/tg-jenkins-bot/frontend/` | Telegram Mini App | `/webapp/` |

Changes to shared patterns should be applied to both.

---

## Frontend Design Philosophy

Both frontends use the same Telegram design language, `--tg-color-*` CSS variable system, and component patterns — but serve different audiences with different UX priorities:

| | Bot Webapp | Config Hub |
|---|-----------|------------|
| **Audience** | End users (Telegram) | Administrators (Telegram / browser) |
| **UX priority** | Strict native Telegram feel, minimal UI | Information density, operational efficiency |
| **Theme** | SDK-injected `--tg-theme-*` + system fallbacks (light/dark) | Same `--tg-color-*` variables with hardcoded dark fallbacks |
| **Deviations** | None — follow Telegram conventions exactly | Minor deviations acceptable for density (e.g., inline expand controls, denser list items, more visible status info) |
| **SDK integration** | Full (`MainButton`, `BackButton`, haptics, `CloudStorage`) | Partial (`BackButton`, haptics) + Emulator support |

The config-hub uses the same CSS variable naming (`--tg-color-*`) and component class names (`.tg-section`, `.tg-list`, `.tg-list-item`) as the bot webapp. This shared design system means a developer maintaining either frontend sees identical structure and naming, even where the UX density differs.

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

- **Config Hub** → `src/config_hub/webapp/` (served at `/webapp-admin/`)
- **Bot Webapp** → `src/tg_jenkins_bot/webapp/` (served at `/webapp/`)

The Python FastAPI service mounts these as `StaticFiles`. No separate static file server. Content-hashed filenames provide cache-busting; the entry HTML revalidates (`no-cache`), sub-resources are cached aggressively.

Build command: `npm run build` (runs `tsc --noEmit && vite build`).

---

## Dev Proxy

Both Vite dev servers proxy API calls to the local gateway:

- Config Hub: `/api/webapp-admin` → `http://localhost:8880`
- Bot Webapp: `/api/webapp` → `http://localhost:8880`

---

## SSE Hooks

Real-time data uses custom `useSSE()` hooks that manage `EventSource` lifecycle, reconnection, and typed event parsing. Both frontends implement their own version tailored to their data model.

---

## Stack-Based Navigation (SPA)

Both frontends use a custom CSS-transform-based stack navigator managed via `useNavigator()`, avoiding standard router packages. In the bot webapp this prevents conflicts with Telegram's native view dynamics; in config-hub it provides consistent navigation with the same animations and patterns.

- **Push**: Renders the new screen offscreen and slides it in from the right (`translateX(100%) -> translateX(0)`), matching native iOS/Telegram aesthetics.
- **Pop**: Slides the active screen out to the right, using a **delayed unmount** pattern. The exiting screen remains in the DOM until the `300ms` slide-out transition finishes. This prevents cleanup triggers (like physical `BackButton.hide()` or `MainButton.hide()`) from firing prematurely mid-animation.
- **Unified Screens**: Detail pages handle multiple states within a single component, transitioning in-place without loading flashes by retaining the last-known state until the final result is fetched.

---

## Native Integration Hooks

Telegram SDK integrations are encapsulated in native-first, declarative React hooks rather than dispersed imperative calls:

- **`useMainButton(config, isActive)`** — Manages the native `tg.MainButton` lifecycle (text, color, disabled state, loading spinner, and click handler swaps).
  - *Singleton Contention Resolution*: When multiple screens are mounted, only the topmost active screen (`isActive = true`) controls the singleton `MainButton`. Inactive hooks yield control and reset the button.
  - *Automatic Cleanup*: Ensures `MainButton` is hidden, progress spinners are stopped, and callbacks are unregistered when the component unmounts.
- **`useCloudStorage(key, fallback)`** — Provides reactive read/write access to `tg.CloudStorage` (wrapping the callback-based API with Promises) and falls back to `localStorage` in browser preview mode. Used to persist preferences like "Notify on completion".

---

Both frontends follow Telegram's design patterns (per `custom-rule.md`) and share the same `--tg-color-*` CSS variable system. The bot webapp integrates with `window.Telegram.WebApp` for theming, haptic feedback, and back-button handling; config-hub uses the same variable names with hardcoded fallback values. 

### Local Telegram WebApp Emulator

To facilitate rapid local development and testing outside the physical Telegram client, both frontends utilize an integrated **Telegram WebApp Emulator** framework:
- **Mock SDK**: Simulates the standard `window.Telegram.WebApp` API interface dynamically when the app is launched in a standard browser window (dev port `8880`).
- **Floating Controls**: Renders reactive mock overlays in the browser for Telegram singletons, including the native `MainButton` and `BackButton`.
- **Parameter Simulation**: Allows developers to toggle between light/dark theme variables and edit test `initData` payloads on-the-fly.
- **Implementation**: Structured cleanly in `emulator.ts` and `emulator.css` under each webapp's frontend source layout.

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
