import { Component } from 'preact';
import type { ComponentChildren } from 'preact';
import { AlertOctagon } from 'lucide-preact';
import { Button } from './Button';

export interface ErrorBoundaryProps {
  children: ComponentChildren;
  title?: string;
  description?: string;
  retryLabel?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
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
      const {
        title = 'Something went wrong',
        description = 'An unexpected error occurred. Please try again.',
        retryLabel = 'Try Again',
      } = this.props;

      return (
        <div
          className="tg-error-boundary"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100%',
            textAlign: 'center',
            padding: 'var(--space-2xl) var(--space-xl)',
            color: 'var(--tg-color-text)',
            gap: 'var(--space-md)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              backgroundColor: 'rgba(255, 59, 48, 0.1)',
              color: 'var(--tg-color-destructive)',
              marginBottom: 'var(--space-sm)',
            }}
          >
            <AlertOctagon size={28} strokeWidth={2} />
          </div>
          <h2 style={{ fontSize: 'var(--font-size-2xl)', fontWeight: 700, margin: 0 }}>
            {title}
          </h2>
          <p style={{ fontSize: 'var(--font-size-base)', color: 'var(--tg-color-hint)', margin: 0, maxWidth: '320px', lineHeight: 'var(--line-height-normal)' }}>
            {description}
          </p>
          <div style={{ marginTop: 'var(--space-lg)', width: '100%', maxWidth: '200px' }}>
            <Button onClick={this.handleRetry} variant="primary">
              {retryLabel}
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
