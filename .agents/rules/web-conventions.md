---
trigger: glob
description: Frontend conventions for Preact + Vite web applications — state, build, and UI design principles.
globs: **/frontend*/**/*.tsx, **/frontend*/**/*.ts, **/frontend*/vite.config.*, **/frontend*/package.json
---

# Web conventions

Triggered when editing frontend TypeScript/TSX files. Defines the architectural principles, shared state contexts, and aesthetic conventions of both frontend applications.

---

## 1. Frontend Stack & Architecture
- **Pure Preact 10 Stack**: Lightweight React alternative. Strictly no raw React library dependencies; use pure Preact 10, Hooks, and native Contexts.
- **Shared Libraries (`libs/`)**:
  - `platform-core`: Standardized platform capabilities, cross-platform Promise-based storage (`usePlatformStorage`), and CTA button management (`usePrimaryButton`).
  - `tg-core-preact`: Native environment providers and viewport size synchronization hooks.
  - `tg-ui-preact`: High-fidelity reusable component library (`Button`, `List`, `ListItem`, `Navigator`, etc.). Must remain strictly independent and never import other workspace libraries.
- **Vite 6 & Static Mounts**: Vite builds compile directly into each Python service static webapp output folder, served directly via FastAPI `StaticFiles` mounts.

---

## 2. Design Philosophy (Telegram Design Language)
- **Telegram Aesthetic Integration**: All components and custom views must natively adhere to Telegram’s design language (using variables like `--tg-color-*` and components like `.tg-section`/`.tg-list`). 
- **Native UI Prominence**: Always prioritize native `window.Telegram.WebApp` client actions (e.g., `tg.showAlert()`, `tg.showPopup()`, `tg.MainButton` for primary CTA overlays) over raw HTML alert elements or custom modal dialogs.
- **UX Separation**:
  - **Bot client**: High-fidelity, strict, minimal interface targeting standard mobile Telegram client users.
  - **Admin dashboard**: Denser layout designed for operational speed, accommodating expand controls, information status lists, and management features while maintaining styling parity.
- **Standalone Desktop Fallback**: Standalone browser/desktop layouts and actions operate on a **best-effort basis only**. Standard storage degrades gracefully to local `localStorage`. Custom HTML emulation scripts and styles are completely removed in favor of direct, native WebApp SDK binding.

---

## 3. UI Flow & Navigation Principles
- **Stack-Based Navigation**: Avoid React Router or default browser history APIs. All navigation must utilize the custom CSS-transform-based screen transition stacks managed via `useNavigator()`.
- **Delayed Unmount Animation**: Exit transitions must implement a delayed unmount pattern (~300ms) to ensure clean visual exits.
- **Screen Visibility Lifecycles**: Use `ScreenActiveContext` (`useScreenActive()`) to coordinate screen-level side effects (like physical back buttons and primary main buttons). Setup and cleanup/unregister routines must check screen visibility to trigger immediately when screens pop, rather than waiting for visual exit transition timers to expire.
- **Native Button Color Resolution**: Native out-of-process client controls (like Telegram's `MainButton`) cannot interpret CSS custom property variable colors (e.g., `var(--...)`). Any CSS variables passed to the platform CTA buttons must be computed and resolved to raw hex values before crossing the platform context boundary.
