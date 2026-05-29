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
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: { componentStack?: string }) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ error: null });
  };

  override render() {
    if (this.state.error) {
      return (
        <div class="error-boundary">
          <AlertOctagon size={36} strokeWidth={2.5} />
          <h2>Something went wrong</h2>
          <p>An unexpected error occurred. Please try again.</p>
          <button class="btn btn-accent" onClick={this.handleRetry}>
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
