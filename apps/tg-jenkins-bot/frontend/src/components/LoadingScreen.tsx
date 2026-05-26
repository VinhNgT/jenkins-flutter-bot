/**
 * LoadingScreen — Skeleton shimmer content preview.
 *
 * Mirrors the structure of MainScreen with placeholder shimmer blocks.
 * Uses the existing .tg-skeleton TGUI classes for the shimmer animation.
 */

export default function LoadingScreen() {
  return (
    <div class="container" style={{ display: 'flex' }}>
      {/* Skeleton header */}
      <header>
        <div>
          <div class="tg-skeleton" style={{ width: '160px', height: '22px', borderRadius: '6px' }} />
          <div class="tg-skeleton" style={{ width: '220px', height: '13px', borderRadius: '4px', marginTop: '6px' }} />
        </div>
      </header>

      {/* Skeleton: Target Option section */}
      <div class="tg-section">
        <div class="tg-section-header">
          <div class="tg-skeleton" style={{ width: '100px', height: '11px', borderRadius: '3px' }} />
        </div>
        <div class="tg-list">
          <div class="tg-list-item" style={{ cursor: 'default' }}>
            <div class="tg-list-item-content">
              <div class="tg-skeleton" style={{ width: '130px', height: '16px', borderRadius: '4px' }} />
              <div class="tg-skeleton" style={{ width: '70px', height: '12px', borderRadius: '3px', marginTop: '4px' }} />
            </div>
          </div>
          <div class="tg-list-item" style={{ cursor: 'default' }}>
            <div class="tg-list-item-content">
              <div class="tg-skeleton" style={{ width: '150px', height: '16px', borderRadius: '4px' }} />
              <div class="tg-skeleton" style={{ width: '90px', height: '12px', borderRadius: '3px', marginTop: '4px' }} />
            </div>
          </div>
        </div>
      </div>

      {/* Skeleton: Custom Branch section */}
      <div class="tg-section">
        <div class="tg-section-header">
          <div class="tg-skeleton" style={{ width: '120px', height: '11px', borderRadius: '3px' }} />
        </div>
        <div class="tg-list">
          <div class="tg-list-item" style={{ cursor: 'default' }}>
            <div class="tg-skeleton" style={{ width: '100%', height: '16px', borderRadius: '4px' }} />
          </div>
        </div>
      </div>

      {/* Skeleton: Active Builds section */}
      <div class="tg-section">
        <div class="tg-section-header">
          <div class="tg-skeleton" style={{ width: '90px', height: '11px', borderRadius: '3px' }} />
        </div>
        <div class="tg-list">
          <div class="tg-empty-row">
            <div class="tg-skeleton" style={{ width: '36px', height: '36px', borderRadius: '50%' }} />
            <div class="tg-skeleton" style={{ width: '200px', height: '13px', borderRadius: '4px', marginTop: '8px' }} />
          </div>
        </div>
      </div>

      {/* Skeleton: Recent Builds section */}
      <div class="tg-section">
        <div class="tg-section-header">
          <div class="tg-skeleton" style={{ width: '110px', height: '11px', borderRadius: '3px' }} />
        </div>
        <div class="tg-list">
          <div class="tg-list-item" style={{ cursor: 'default' }}>
            <div class="tg-list-item-content">
              <div class="tg-skeleton" style={{ width: '140px', height: '16px', borderRadius: '4px' }} />
              <div class="tg-skeleton" style={{ width: '100px', height: '12px', borderRadius: '3px', marginTop: '4px' }} />
            </div>
          </div>
          <div class="tg-list-item" style={{ cursor: 'default' }}>
            <div class="tg-list-item-content">
              <div class="tg-skeleton" style={{ width: '120px', height: '16px', borderRadius: '4px' }} />
              <div class="tg-skeleton" style={{ width: '80px', height: '12px', borderRadius: '3px', marginTop: '4px' }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
