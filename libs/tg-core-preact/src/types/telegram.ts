/**
 * Ambient type declarations for the Telegram Web App SDK.
 *
 * Full SDK reference: https://core.telegram.org/bots/webapps
 */

export interface TelegramThemeParams {
  bg_color?: string;
  secondary_bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  destructive_text_color?: string;
  section_bg_color?: string;
  section_header_text_color?: string;
  subtitle_text_color?: string;
  header_bg_color?: string;
  section_separator_color?: string;
  bottom_bar_bg_color?: string;
}

export interface TelegramMainButton {
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
  show(): void;
  hide(): void;
  enable(): void;
  disable(): void;
  showProgress(leaveActive?: boolean): void;
  hideProgress(): void;
  setParams(params: {
    text?: string;
    color?: string;
    text_color?: string;
    is_active?: boolean;
    is_visible?: boolean;
  }): void;
}

export interface TelegramBackButton {
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
  show(): void;
  hide(): void;
}

export interface TelegramHapticFeedback {
  selectionChanged(): void;
  impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
  notificationOccurred(type: 'error' | 'success' | 'warning'): void;
}

export interface TelegramPopupButton {
  id: string;
  type?: 'default' | 'ok' | 'close' | 'cancel' | 'destructive';
  text?: string;
}

export interface TelegramPopupParams {
  title?: string;
  message: string;
  buttons?: TelegramPopupButton[];
}

export interface TelegramCloudStorage {
  setItem(key: string, value: string, callback?: (err: string | null, stored: boolean) => void): void;
  getItem(key: string, callback: (err: string | null, value: string) => void): void;
  getItems(keys: string[], callback: (err: string | null, values: Record<string, string>) => void): void;
  removeItem(key: string, callback?: (err: string | null, removed: boolean) => void): void;
  getKeys(callback: (err: string | null, keys: string[]) => void): void;
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: {
      id: number;
      first_name: string;
      username?: string;
    };
    chat?: {
      id: number;
      type: string;
    };
    start_param?: string;
  };
  colorScheme: 'light' | 'dark';
  themeParams: TelegramThemeParams;
  MainButton: TelegramMainButton;
  BackButton: TelegramBackButton;
  HapticFeedback: TelegramHapticFeedback;
  CloudStorage: TelegramCloudStorage;

  isFullscreen?: boolean;
  requestFullscreen?(): void;
  exitFullscreen?(): void;
  readTextFromClipboard?(callback: (text: string) => void): void;
  openLink?(url: string, options?: { try_instant_view?: boolean }): void;
  ready(): void;
  expand(): void;
  disableVerticalSwipes?(): void;
  enableVerticalSwipes?(): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  setBottomBarColor?(color: string): void;
  showPopup(params: TelegramPopupParams, callback?: (buttonId: string) => void): void;
  showAlert(message: string, callback?: () => void): void;
  showConfirm(message: string, callback?: (isConfirmed: boolean) => void): void;
  openTelegramLink(url: string): void;
  onEvent(event: string, callback: (...args: any[]) => void): void;
  offEvent(event: string, callback: (...args: any[]) => void): void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
    };
  }
}
