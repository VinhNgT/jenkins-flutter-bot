/**
 * Vitest global setup — provides a minimal Telegram WebApp mock.
 *
 * Stubs the window.Telegram.WebApp global with enough surface area
 * to test hooks that depend on the SDK (useMainButton, useCloudStorage).
 */

import { vi } from 'vitest';

/** Minimal MainButton stub with spyable methods. */
const MainButton = {
  text: '',
  color: '#2481cc',
  textColor: '#ffffff',
  isVisible: false,
  isActive: true,
  isProgressVisible: false,
  setText: vi.fn(function(this: typeof MainButton, t: string) { this.text = t; }),
  show: vi.fn(function(this: typeof MainButton) { this.isVisible = true; }),
  hide: vi.fn(function(this: typeof MainButton) { this.isVisible = false; }),
  enable: vi.fn(function(this: typeof MainButton) { this.isActive = true; }),
  disable: vi.fn(function(this: typeof MainButton) { this.isActive = false; }),
  showProgress: vi.fn(function(this: typeof MainButton) { this.isProgressVisible = true; }),
  hideProgress: vi.fn(function(this: typeof MainButton) { this.isProgressVisible = false; }),
  onClick: vi.fn(),
  offClick: vi.fn(),
  setParams: vi.fn(),
};

/** Minimal BackButton stub. */
const BackButton = {
  isVisible: false,
  show: vi.fn(function(this: typeof BackButton) { this.isVisible = true; }),
  hide: vi.fn(function(this: typeof BackButton) { this.isVisible = false; }),
  onClick: vi.fn(),
  offClick: vi.fn(),
};

/** Minimal CloudStorage stub. */
const CloudStorage = {
  getItem: vi.fn((_key: string, cb: (err: null, val: string) => void) => cb(null, '')),
  setItem: vi.fn((_key: string, _val: string, cb?: () => void) => cb?.()),
  removeItem: vi.fn((_key: string, cb?: () => void) => cb?.()),
};

const mockWebApp = {
  initData: 'mock-init-data',
  initDataUnsafe: {
    user: { id: 12345, first_name: 'Test', language_code: 'en' },
    chat: { id: -100123, type: 'group' },
  },
  version: '7.10',
  platform: 'web',
  colorScheme: 'light' as const,
  themeParams: {
    bg_color: '#ffffff',
    text_color: '#000000',
    hint_color: '#999999',
    link_color: '#2481cc',
    button_color: '#2481cc',
    button_text_color: '#ffffff',
    secondary_bg_color: '#f0f0f0',
  },
  isExpanded: true,
  viewportHeight: 600,
  viewportStableHeight: 600,
  MainButton,
  BackButton,
  CloudStorage,
  ready: vi.fn(),
  expand: vi.fn(),
  close: vi.fn(),
  setHeaderColor: vi.fn(),
  setBackgroundColor: vi.fn(),
  onEvent: vi.fn(),
  offEvent: vi.fn(),
  showAlert: vi.fn(),
  showConfirm: vi.fn(),
  showPopup: vi.fn(),
  disableVerticalSwipes: vi.fn(),
  enableVerticalSwipes: vi.fn(),
  setBottomBarColor: vi.fn(),
  HapticFeedback: {
    impactOccurred: vi.fn(),
    notificationOccurred: vi.fn(),
    selectionChanged: vi.fn(),
  },
};

// Install the mock globally before all tests
(globalThis as any).window ??= globalThis;
(window as any).Telegram = { WebApp: mockWebApp };
