import { useState } from 'preact/hooks';
import { AlertOctagon, Plus, Copy, Check } from 'lucide-preact';
import { usePlatform } from 'platform-core';
import { Scaffold, List, ListItem, Button } from 'tg-ui-preact';
import { useToast } from '../context/ToastContext';
import type { ApiErrorDetail } from '../types';

interface ErrorScreenProps {
  title: string;
  description: string;
  detail: ApiErrorDetail | null;
}

/**
 * ErrorScreen — Error/access-denied barrier view.
 *
 * Renders contextual CTAs based on the error type inside a unified Scaffold
 * using shared design system primitives (Scaffold, List, ListItem, Button).
 */
export default function ErrorScreen({ title, description, detail }: ErrorScreenProps) {
  const { haptic, openLink } = usePlatform();
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);

  function handleAddToGroup() {
    if (!detail?.bot_username) return;
    haptic.impact('medium');
    openLink(`https://t.me/${detail.bot_username}?startgroup=auth`);
  }

  async function handleCopyChatId() {
    if (!detail?.chat_id) return;
    haptic.impact('light');
    try {
      await navigator.clipboard.writeText(String(detail.chat_id));
      setCopied(true);
      showToast('Copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast('Failed to copy. Please manually copy the ID.', 'error');
    }
  }

  const isPrivateDisabled = detail?.error === 'private_chat_disabled';
  const isGroupUnauthorized = detail?.error === 'group_not_authorized';

  return (
    <Scaffold>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-xl) var(--space-md)',
        textAlign: 'center',
        flex: 1
      }}>
        <div style={{ color: 'var(--tg-color-destructive)', marginBottom: 'var(--space-lg)' }}>
          <AlertOctagon size={64} />
        </div>

        <h1 className="panel-title" style={{ fontSize: '24px', marginBottom: 'var(--space-md)' }}>
          {title}
        </h1>

        <p className="panel-desc" style={{ fontSize: '15px', color: 'var(--tg-color-hint)', marginBottom: 'var(--space-xl)', maxWidth: '400px', lineHeight: 1.5 }}>
          {description}
        </p>

        {isPrivateDisabled && detail.bot_username && (
          <div style={{ width: '100%', maxWidth: '280px' }}>
            <Button variant="primary" onClick={handleAddToGroup}>
              <Plus size={20} />
              <span>Add Bot to Group</span>
            </Button>
          </div>
        )}

        {isGroupUnauthorized && detail.chat_id && (
          <div style={{ width: '100%', maxWidth: '320px', marginTop: 'var(--space-sm)' }}>
            <List footer="Provide this ID to your bot administrator to allowlist this group.">
              <ListItem
                title="Current Chat ID"
                subtitle={<span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-base)', fontWeight: 600 }}>{detail.chat_id}</span>}
                rightElement={
                  <button
                    onClick={handleCopyChatId}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: copied ? 'var(--tg-color-success)' : 'var(--tg-color-link)',
                      cursor: 'pointer',
                      padding: 'var(--space-xs)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}
                    title="Copy Chat ID"
                  >
                    {copied ? <Check size={20} /> : <Copy size={20} />}
                  </button>
                }
              />
            </List>
          </div>
        )}
      </div>
    </Scaffold>
  );
}
