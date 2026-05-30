import { useEffect, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';

interface ShimmerProps {
  /** Width width dimension (e.g. '100%', '80px') */
  width?: string | number;
  /** Height height dimension */
  height?: string | number;
  /** Border radius parameter */
  borderRadius?: string;
  /** Custom CSS classes */
  className?: string;
  /** Custom inline style overrides */
  style?: Record<string, string | number>;
}

export function Shimmer({
  width = '100%',
  height = '14px',
  borderRadius = 'var(--radius-sm)',
  className = '',
  style,
}: ShimmerProps) {
  return (
    <div
      className={`tg-skeleton ${className}`}
      style={{
        width,
        height,
        borderRadius,
        ...style,
      }}
    />
  );
}

interface SkeletonContainerProps {
  /** The reactive loading status state */
  loading: boolean;
  /** Skeleton layout component structure to display while loading */
  skeleton: ComponentChildren;
  /** The final actual loaded component content */
  children: ComponentChildren;
  /** Custom CSS classes */
  className?: string;
}

export function SkeletonContainer({
  loading,
  skeleton,
  children,
  className = '',
}: SkeletonContainerProps) {
  const [renderSkeleton, setRenderSkeleton] = useState(loading);
  const [fadePhase, setFadePhase] = useState<'loading' | 'fading-out' | 'done'>(
    loading ? 'loading' : 'done'
  );

  useEffect(() => {
    if (loading) {
      setRenderSkeleton(true);
      setFadePhase('loading');
    } else if (fadePhase === 'loading') {
      // Begin the parallel cross-fade transition
      setFadePhase('fading-out');
    }
  }, [loading]);

  const handleTransitionEnd = (e: TransitionEvent) => {
    // Only capture opacity transition events
    if (e.propertyName === 'opacity' && fadePhase === 'fading-out') {
      setRenderSkeleton(false);
      setFadePhase('done');
    }
  };

  return (
    <div className={`tg-skeleton-container ${className}`}>
      {/* 1. Skeleton Overlay Layer (Fades out when loaded) */}
      {renderSkeleton && (
        <div
          className={`tg-skeleton-overlay ${fadePhase === 'fading-out' ? 'tg-skeleton-fade-out' : ''}`}
          onTransitionEnd={handleTransitionEnd}
        >
          {skeleton}
        </div>
      )}

      {/* 2. Actual Content Layer (Fades in when loaded) */}
      <div
        className={`tg-skeleton-content ${
          fadePhase === 'loading'
            ? 'tg-skeleton-fade-out'
            : fadePhase === 'fading-out'
            ? 'tg-skeleton-fade-in'
            : ''
        }`}
        style={{
          opacity: fadePhase === 'loading' ? 0 : 1,
          transition: 'opacity 250ms ease-in',
        }}
      >
        {children}
      </div>
    </div>
  );
}
