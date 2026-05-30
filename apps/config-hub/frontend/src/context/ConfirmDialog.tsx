/**
 * Promise-based confirm dialog provider.
 * Uses native platform dialog prompts when available (e.g. Telegram),
 * otherwise falls back to a clean, theme-aware HTML5 modal dialog.
 * Exposes a Promise-based API via useConfirm().
 */

import { createContext } from 'preact';
import { useCallback, useContext, useRef, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import { usePlatform } from 'platform-core';
import { Dialog } from 'tg-ui-preact';


interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(async () => false);

export function ConfirmProvider({ children }: { children: ComponentChildren }) {
  const platform = usePlatform();
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const confirm = useCallback((opts: ConfirmOptions): Promise<boolean> => {
    if (platform.hasNativePopup) {
      return platform.showConfirm({
        title: opts.title,
        message: opts.message,
        confirmLabel: opts.confirmLabel,
        danger: opts.danger,
      });
    }

    setOptions(opts);
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      requestAnimationFrame(() => dialogRef.current?.showModal());
    });
  }, [platform]);

  function close(result: boolean) {
    dialogRef.current?.close();
    resolveRef.current?.(result);
    resolveRef.current = null;
    setOptions(null);
  }

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Dialog
        dialogRef={dialogRef}
        onCancel={(e) => {
          e.preventDefault();
          close(false);
        }}
      >
        {options && (
          <>
            <h2 class="dialog-title">{options.title}</h2>
            <p class="dialog-msg">{options.message}</p>
            <div class="dialog-actions">
              <button class="btn btn-secondary" onClick={() => close(false)}>
                Cancel
              </button>
              <button
                class={`btn ${options.danger ? 'btn-danger' : 'btn-accent'}`}
                onClick={() => close(true)}
              >
                {options.confirmLabel ?? 'Confirm'}
              </button>
            </div>
          </>
        )}
      </Dialog>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}
