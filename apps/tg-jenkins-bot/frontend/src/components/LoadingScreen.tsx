import { Scaffold, List, ListItem, Shimmer } from 'tg-ui-preact';

/**
 * LoadingScreen — Skeleton shimmer content preview.
 *
 * Wraps the loading layout in a unified Scaffold and renders shimmer blocks
 * using the shared generic Shimmer, List, and ListItem primitives.
 */
export default function LoadingScreen() {
  return (
    <Scaffold title="Loading..." subtitle="Synchronizing system environment">
      {/* Deployment Target Options Skeleton */}
      <List header="Deployment Target">
        <ListItem
          title={<Shimmer width="130px" height="16px" />}
          subtitle={<Shimmer width="70px" height="12px" />}
          disabled
        />
        <ListItem
          title={<Shimmer width="150px" height="16px" />}
          subtitle={<Shimmer width="90px" height="12px" />}
          disabled
        />
      </List>

      {/* Custom Option Skeleton */}
      <List header="Custom Option">
        <ListItem
          title={<Shimmer width="100%" height="16px" />}
          disabled
        />
      </List>

      {/* Active Deployments Skeleton */}
      <List header="Active Deployments">
        <div className="tg-empty-row">
          <Shimmer width="36px" height="36px" borderRadius="var(--radius-round)" />
          <Shimmer width="200px" height="13px" className="tg-skeleton" style={{ marginTop: 'var(--space-sm)' }} />
        </div>
      </List>

      {/* Recent History Skeleton */}
      <List header="Recent Build History">
        <ListItem
          title={<Shimmer width="140px" height="16px" />}
          subtitle={<Shimmer width="100px" height="12px" />}
          disabled
        />
        <ListItem
          title={<Shimmer width="120px" height="16px" />}
          subtitle={<Shimmer width="80px" height="12px" />}
          disabled
        />
      </List>
    </Scaffold>
  );
}
