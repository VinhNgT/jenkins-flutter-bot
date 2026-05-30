import type { ComponentChildren, Ref } from 'preact';

export interface DialogProps {
  /** Reference to the native HTML5 dialog element for imperative controls (.showModal() / .close()) */
  dialogRef?: Ref<HTMLDialogElement>;
  /** Callback triggered when the dialog is cancelled or dismissed (e.g. Escape key) */
  onCancel?: (e: Event) => void;
  /** Content children to render within the dialog frame */
  children: ComponentChildren;
  /** Optional custom CSS classes */
  className?: string;
  /** Optional unique element ID */
  id?: string;
}

export function Dialog({ dialogRef, onCancel, children, className = '', id }: DialogProps) {
  return (
    <dialog
      ref={dialogRef}
      id={id}
      className={`confirm-dialog ${className}`}
      onCancel={onCancel}
    >
      {children}
    </dialog>
  );
}
