/**
 * Telegram SDK Emulator — Browser Development Mode
 *
 * Injects a mock window.Telegram.WebApp when running outside Telegram
 * on localhost. Does nothing in production or inside the Telegram client.
 *
 * This module is dynamically imported by main.tsx only when:
 * - The page is on localhost
 * - No real Telegram SDK is detected
 *
 * It must execute synchronously once imported so that TelegramProvider
 * sees the mock SDK on the next render cycle.
 */

import './styles/emulator.css';

// Setup base namespace — unconditionally assign since this is the emulator entry point
if (!window.Telegram) {
  window.Telegram = { WebApp: {} as TelegramWebApp };
}
const WebApp = window.Telegram.WebApp;

// Theme presets
const lightTheme: TelegramThemeParams = {
  bg_color: '#ffffff',
  secondary_bg_color: '#f4f4f7',
  text_color: '#000000',
  hint_color: '#8e8e93',
  link_color: '#007ee5',
  button_color: '#2481cc',
  button_text_color: '#ffffff',
  destructive_text_color: '#ff3b30',
  section_bg_color: '#ffffff',
  section_header_text_color: '#8e8e93',
  subtitle_text_color: '#8e8e93',
  header_bg_color: '#f4f4f7',
  section_separator_color: 'rgba(0, 0, 0, 0.08)',
  bottom_bar_bg_color: '#f4f4f7',
};

const darkTheme: TelegramThemeParams = {
  bg_color: '#1c242c',
  secondary_bg_color: '#0f171e',
  text_color: '#ffffff',
  hint_color: '#708499',
  link_color: '#5288c1',
  button_color: '#5288c1',
  button_text_color: '#ffffff',
  destructive_text_color: '#ff3b30',
  section_bg_color: '#1c242c',
  section_header_text_color: '#708499',
  subtitle_text_color: '#708499',
  header_bg_color: '#0f171e',
  section_separator_color: 'rgba(255, 255, 255, 0.08)',
  bottom_bar_bg_color: '#0f171e',
};

function getThemeParams(): TelegramThemeParams {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? darkTheme : lightTheme;
}

// Properties
WebApp.initData = 'preview';
WebApp.initDataUnsafe = {
  user: { id: 12345, first_name: 'Preview', username: 'preview_dev' },
};
WebApp.colorScheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
WebApp.themeParams = getThemeParams();

// Events system
const events: Record<string, Array<() => void>> = {};
WebApp.onEvent = (eventType: string, callback: () => void) => {
  if (!events[eventType]) events[eventType] = [];
  events[eventType]!.push(callback);
};
WebApp.offEvent = (eventType: string, callback: () => void) => {
  const handlers = events[eventType];
  if (handlers) {
    const idx = handlers.indexOf(callback);
    if (idx !== -1) handlers.splice(idx, 1);
  }
};

// Auto-sync dark/light mode
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
  WebApp.colorScheme = e.matches ? 'dark' : 'light';
  WebApp.themeParams = getThemeParams();
  console.log(`🔧 [Emulator] Theme changed to ${WebApp.colorScheme}`);
  events['themeChanged']?.forEach((cb) => { try { cb(); } catch (err) { console.error(err); } });
});

// Basic methods
WebApp.ready = () => console.log('🔧 [Emulator] WebApp.ready()');
WebApp.expand = () => console.log('🔧 [Emulator] WebApp.expand()');
WebApp.setHeaderColor = (c: string) => console.log(`🔧 [Emulator] setHeaderColor("${c}")`);
WebApp.setBackgroundColor = (c: string) => console.log(`🔧 [Emulator] setBackgroundColor("${c}")`);
WebApp.setBottomBarColor = (c: string) => console.log(`🔧 [Emulator] setBottomBarColor("${c}")`);
WebApp.disableVerticalSwipes = () => console.log('🔧 [Emulator] disableVerticalSwipes()');
WebApp.enableVerticalSwipes = () => console.log('🔧 [Emulator] enableVerticalSwipes()');
WebApp.openTelegramLink = (url: string) => { console.log(`🔧 [Emulator] openTelegramLink("${url}")`); window.open(url, '_blank'); };

// Popup
WebApp.showPopup = (params: TelegramPopupParams, callback?: (buttonId: string) => void) => {
  console.log('🔧 [Emulator] showPopup()', params);

  document.querySelector('.emu-popup-overlay')?.remove();

  const overlay = document.createElement('div');
  overlay.className = 'emu-popup-overlay';

  const card = document.createElement('div');
  card.className = 'emu-popup-card';

  if (params.title) {
    const title = document.createElement('h3');
    title.innerText = params.title;
    card.appendChild(title);
  }
  if (params.message) {
    const message = document.createElement('p');
    message.innerText = params.message;
    card.appendChild(message);
  }

  const btnContainer = document.createElement('div');
  btnContainer.className = 'emu-popup-buttons';

  const buttons = params.buttons?.length ? params.buttons : [{ id: '', type: 'ok' as const, text: 'OK' }];
  buttons.forEach((spec) => {
    const btn = document.createElement('button');
    btn.className = 'emu-popup-btn';
    if (spec.type === 'destructive') btn.classList.add('emu-popup-destructive');
    if (spec.type === 'cancel') btn.classList.add('emu-popup-cancel');
    btn.innerText = spec.text ?? 'OK';
    btn.addEventListener('click', () => { overlay.remove(); callback?.(spec.id); });
    btnContainer.appendChild(btn);
  });

  card.appendChild(btnContainer);
  overlay.appendChild(card);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) { overlay.remove(); callback?.(''); } });
  document.body.appendChild(overlay);
};

// HapticFeedback
WebApp.HapticFeedback = {
  selectionChanged: () => { console.log('📳 [Haptic] selectionChanged'); try { navigator.vibrate?.(10); } catch { /* noop */ } },
  impactOccurred: (style) => { console.log('📳 [Haptic] impactOccurred:', style); const d = style === 'heavy' ? 40 : style === 'medium' ? 25 : 12; try { navigator.vibrate?.(d); } catch { /* noop */ } },
  notificationOccurred: (type) => { console.log('📳 [Haptic] notificationOccurred:', type); const d = type === 'error' ? 60 : type === 'warning' ? 40 : 20; try { navigator.vibrate?.(d); } catch { /* noop */ } },
};

// CloudStorage — localStorage-backed mock for emulator
const CS_PREFIX = '__tg_cloud_';
WebApp.CloudStorage = {
  setItem(key, value, cb) {
    try { localStorage.setItem(CS_PREFIX + key, value); cb?.(null, true); }
    catch (e) { cb?.(String(e), false); }
  },
  getItem(key, cb) {
    try { cb(null, localStorage.getItem(CS_PREFIX + key) ?? ''); }
    catch (e) { cb(String(e), ''); }
  },
  getItems(keys, cb) {
    try {
      const result: Record<string, string> = {};
      for (const k of keys) result[k] = localStorage.getItem(CS_PREFIX + k) ?? '';
      cb(null, result);
    } catch (e) { cb(String(e), {}); }
  },
  removeItem(key, cb) {
    try { localStorage.removeItem(CS_PREFIX + key); cb?.(null, true); }
    catch (e) { cb?.(String(e), false); }
  },
  getKeys(cb) {
    try {
      const keys: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k?.startsWith(CS_PREFIX)) keys.push(k.slice(CS_PREFIX.length));
      }
      cb(null, keys);
    } catch (e) { cb(String(e), []); }
  },
};

// MainButton
const MainButton: TelegramMainButton & { _onClickCb: (() => void) | null; _visible: boolean; _enabled: boolean; _text: string; _color: string; _textColor: string; _progress: boolean; _updateDOM(): void } = {
  _onClickCb: null, _visible: false, _enabled: true, _text: 'CONTINUE', _color: '#2481cc', _textColor: '#ffffff', _progress: false,
  onClick(cb) { this._onClickCb = cb; },
  offClick(cb) { if (this._onClickCb === cb) this._onClickCb = null; },
  show() { this._visible = true; this._updateDOM(); },
  hide() { this._visible = false; this._updateDOM(); },
  enable() { this._enabled = true; this._updateDOM(); },
  disable() { this._enabled = false; this._updateDOM(); },
  setParams(params) {
    if (params.text !== undefined) this._text = params.text;
    if (params.color !== undefined) this._color = params.color;
    if (params.text_color !== undefined) this._textColor = params.text_color;
    if (params.is_active !== undefined) this._enabled = params.is_active;
    if (params.is_visible !== undefined) this._visible = params.is_visible;
    this._updateDOM();
  },
  showProgress(leaveActive = false) { this._progress = true; if (!leaveActive) this._enabled = false; this._updateDOM(); },
  hideProgress() { this._progress = false; this._enabled = true; this._updateDOM(); },
  _updateDOM() {
    const btn = document.querySelector('.emu-main-button') as HTMLButtonElement | null;
    if (!btn) return;
    btn.style.display = this._visible ? 'flex' : 'none';
    btn.disabled = !this._enabled;
    btn.style.backgroundColor = this._color;
    btn.style.color = this._textColor;
    const textEl = btn.querySelector('.emu-main-button-text') as HTMLElement | null;
    const spinnerEl = btn.querySelector('.emu-main-button-spinner') as HTMLElement | null;
    if (textEl) textEl.innerText = this._text;
    if (spinnerEl) spinnerEl.style.display = this._progress ? 'inline-flex' : 'none';
  },
};
WebApp.MainButton = MainButton;

// BackButton
const BackButton: TelegramBackButton & { _onClickCb: (() => void) | null; _visible: boolean; _updateDOM(): void } = {
  _onClickCb: null, _visible: false,
  onClick(cb) { this._onClickCb = cb; },
  offClick(cb) { if (this._onClickCb === cb) this._onClickCb = null; },
  show() { this._visible = true; this._updateDOM(); },
  hide() { this._visible = false; this._updateDOM(); },
  _updateDOM() {
    const btn = document.querySelector('.emu-back-button') as HTMLButtonElement | null;
    if (btn) btn.style.display = this._visible ? 'flex' : 'none';
  },
};
WebApp.BackButton = BackButton;

// DOM injection — runs once when this module is imported
function initDOM() {
  // Badge
  const badge = document.createElement('div');
  badge.className = 'emu-badge';
  badge.innerText = '🔧 EMULATOR';
  document.body.appendChild(badge);

  // MainButton
  const mainBtn = document.createElement('button');
  mainBtn.className = 'emu-main-button';
  mainBtn.style.display = 'none';
  mainBtn.innerHTML = `
    <span class="emu-main-button-text">CONTINUE</span>
    <span class="emu-main-button-spinner" style="display: none; align-items: center; justify-content: center; width: 18px; height: 18px;">
      <svg class="spinner-ios" style="width: 18px; height: 18px; animation-duration:0.65s; color: inherit;" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" stroke="rgba(255, 255, 255, 0.15)" stroke-width="3"></circle>
        <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="3" stroke-linecap="round"></path>
      </svg>
    </span>
  `;
  mainBtn.addEventListener('click', () => { if (MainButton._onClickCb) MainButton._onClickCb(); });
  document.body.appendChild(mainBtn);

  // BackButton
  const backBtn = document.createElement('button');
  backBtn.className = 'emu-back-button';
  backBtn.style.display = 'none';
  backBtn.innerHTML = `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <line x1="19" y1="12" x2="5" y2="12"></line>
      <polyline points="12 19 5 12 12 5"></polyline>
    </svg>
  `;
  backBtn.addEventListener('click', () => { if (BackButton._onClickCb) BackButton._onClickCb(); });
  document.body.appendChild(backBtn);

  MainButton._updateDOM();
  BackButton._updateDOM();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDOM);
} else {
  initDOM();
}

console.log(
  '%c🔧 Telegram SDK Emulator Active %c\nRunning in local development mode. initData="preview"',
  'background: #2481cc; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;',
  'color: #708499;',
);
