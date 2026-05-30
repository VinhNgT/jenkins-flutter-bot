/**
 * ErrorScreen — Error/access-denied barrier view.
 *
 * Renders contextual CTAs based on the error type:
 * - private_chat_disabled → "Add Bot to Group" button
 * - group_not_authorized → Chat ID copy panel
 * - Generic errors → simple error display with BackButton retry
 */

import { useState } from 'preact/hooks';
import { AlertOctagon, Plus } from 'lucide-preact';
import { useTelegram } from '../context/TelegramContext';
import { useToast } from '../context/ToastContext';
import type { ApiErrorDetail } from '../types';

interface ErrorScreenProps {
  title: string;
  description: string;
  detail: ApiErrorDetail | null;
}

export default function ErrorScreen({ title, description, detail }: ErrorScreenProps) {
  const { tg, haptic } = useTelegram();
  const { showToast } = useToast();
  const [copyLabel, setCopyLabel] = useState('📋');

  function handleAddToGroup() {
    if (!detail?.bot_username || !tg) return;
    haptic.impact('medium');
    tg.openTelegramLink(`https://t.me/${detail.bot_username}?startgroup=auth`);
  }

  async function handleCopyChatId() {
    if (!detail?.chat_id) return;
    haptic.impact('light');
    try {
      await navigator.clipboard.writeText(String(detail.chat_id));
      setCopyLabel('✅');
      showToast('Copied to clipboard');
      setTimeout(() => setCopyLabel('📋'), 2000);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div class="screen active">
      <div class="screen-icon error">
        <AlertOctagon size={36} strokeWidth={2.5} />
      </div>
      <h2 class="screen-title">{title}</h2>
      <p class="screen-description">{description}</p>

      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {/* CTA: Add bot to group */}
        {detail?.error === 'private_chat_disabled' && detail.bot_username && (
          <div style={{ marginTop: 'var(--space-xl)', width: '100%', maxWidth: '280px' }}>
            <button class="tg-primary-button" onClick={handleAddToGroup}>
              <Plus size={18} strokeWidth={2.5} />
              <span>Add Bot to Group</span>
            </button>
          </div>
        )}

        {/* CTA: Copy chat ID */}
        {detail?.error === 'group_not_authorized' && detail.chat_id && (
          <div class="tg-action-card">
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--tg-color-subtitle)', fontWeight: 700, textAlign: 'left', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              YOUR CHAT ID:
            </div>
            <div class="tg-copy-container">
              <input
                type="text"
                readonly
                value={String(detail.chat_id)}
                class="tg-copy-field"
                onClick={(e) => (e.target as HTMLInputElement).select()}
              />
              <button class="tg-copy-button" onClick={handleCopyChatId}>
                {copyLabel}
              </button>
            </div>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--tg-color-hint)', lineHeight: 1.45, textAlign: 'center', marginTop: 'var(--space-xs)' }}>
              Share this ID with your system administrator to secure authorized access.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
