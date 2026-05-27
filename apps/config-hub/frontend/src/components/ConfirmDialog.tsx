/**
 * ConfirmDialog — Modal confirmation dialog.
 *
 * Uses the native <dialog> element for accessibility.
 * Exposes a Promise-based API via useConfirm().
 */

import { createContext } from 'preact';
import { useCallback, useContext, useRef, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(async () => false);

export function ConfirmProvider({ children }: { children: ComponentChildren }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const confirm = useCallback((opts: ConfirmOptions): Promise<boolean> => {
    setOptions(opts);
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      requestAnimationFrame(() => dialogRef.current?.showModal());
    });
  }, []);

  function close(result: boolean) {
    dialogRef.current?.close();
    resolveRef.current?.(result);
    resolveRef.current = null;
    setOptions(null);
  }

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <dialog
        ref={dialogRef}
        class="confirm-dialog"
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
      </dialog>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}
