/**
 * Toast — Sliding notification banner.
 *
 * Rendered by ToastProvider. Uses the existing .tg-toast TGUI classes.
 */

import type { ReadonlySignal } from '@preact/signals';
import { Check } from 'lucide-preact';

interface ToastState {
  message: string;
  type: 'success' | 'error';
  visible: boolean;
}

interface ToastProps {
  state: ReadonlySignal<ToastState>;
}

export default function Toast({ state }: ToastProps) {
  const { message, type, visible } = state.value;

  const classes = [
    'tg-toast',
    visible ? 'active' : '',
    type === 'error' ? 'toast-error' : '',
  ].filter(Boolean).join(' ');

  return (
    <div class={classes}>
      <div class="tg-toast-icon">
        <Check size={20} strokeWidth={2.5} />
      </div>
      <span>{message}</span>
    </div>
  );
}
