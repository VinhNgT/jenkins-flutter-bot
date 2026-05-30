interface SpinnerProps {
  /** Diameter size in pixels */
  size?: number;
  /** Stroke color token */
  color?: string;
  /** Custom CSS classes */
  className?: string;
}

export function Spinner({
  size = 24,
  color = 'var(--tg-color-link)',
  className = '',
}: SpinnerProps) {
  return (
    <svg
      className={`spinner-ios ${className}`}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      style={{
        animation: 'rotateSpinner 0.8s linear infinite',
        color: color,
        display: 'inline-block',
        flexShrink: 0,
      }}
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeDasharray="42 18"
        strokeLinecap="round"
      />
    </svg>
  );
}
