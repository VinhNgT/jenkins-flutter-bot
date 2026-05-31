import type { ReadonlySignal } from '@preact/signals';
import { Check, X } from 'lucide-preact';
import { Toast as SharedToast } from 'tg-ui-preact';

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
  const Icon = type === 'error' ? X : Check;

  return (
    <SharedToast
      message={message}
      active={visible}
      type={type}
      icon={<Icon size={20} strokeWidth={2.5} />}
    />
  );
}

