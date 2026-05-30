/**
 * Ambient type declarations for the Telegram Web App SDK.
 *
 * Covers only the subset of the API surface used by this application.
 * Full SDK reference: https://core.telegram.org/bots/webapps
 */

interface TelegramThemeParams {
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

interface TelegramMainButton {
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

interface TelegramBackButton {
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
  show(): void;
  hide(): void;
}

interface TelegramHapticFeedback {
  selectionChanged(): void;
  impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
  notificationOccurred(type: 'error' | 'success' | 'warning'): void;
}

interface TelegramPopupButton {
  id: string;
  type?: 'default' | 'ok' | 'close' | 'cancel' | 'destructive';
  text?: string;
}

interface TelegramPopupParams {
  title?: string;
  message: string;
  buttons?: TelegramPopupButton[];
}

interface TelegramCloudStorage {
  setItem(key: string, value: string, callback?: (err: string | null, stored: boolean) => void): void;
  getItem(key: string, callback: (err: string | null, value: string) => void): void;
  getItems(keys: string[], callback: (err: string | null, values: Record<string, string>) => void): void;
  removeItem(key: string, callback?: (err: string | null, removed: boolean) => void): void;
  getKeys(callback: (err: string | null, keys: string[]) => void): void;
}

interface TelegramWebApp {
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
  onEvent(event: string, callback: () => void): void;
  offEvent(event: string, callback: () => void): void;
}

interface Window {
  Telegram?: {
    WebApp: TelegramWebApp;
  };
}
