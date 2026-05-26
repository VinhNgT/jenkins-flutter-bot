/**
 * ErrorBoundary — Catches rendering exceptions and shows a recovery screen.
 *
 * Prevents full-app blank screens from uncaught component errors.
 */

import { Component } from 'preact';
import type { ComponentChildren } from 'preact';
import { AlertOctagon } from 'lucide-preact';

interface Props {
  children: ComponentChildren;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div class="screen active">
          <div class="screen-icon error">
            <AlertOctagon size={36} strokeWidth={2.5} />
          </div>
          <h2 class="screen-title">Something went wrong</h2>
          <p class="screen-description">
            An unexpected error occurred. Please try again.
          </p>
          <div style={{ marginTop: '24px', width: '100%', maxWidth: '280px' }}>
            <button class="tg-primary-button" onClick={this.handleRetry}>
              <span>Try Again</span>
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
