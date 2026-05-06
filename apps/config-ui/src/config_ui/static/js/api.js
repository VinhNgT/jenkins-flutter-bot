/* Centralized API client — all fetch calls go through here. */

// eslint-disable-next-line no-unused-vars
const API = {
  /** @returns {Promise<Object|null>} */
  async getConfig() {
    try {
      const res = await fetch('/api/config');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      Toast.show(`Failed to load config: ${err.message}`, 'error');
      return null;
    }
  },

  /**
   * Save config for a single scope.
   * @param {'bot'|'agent'|'ui'} scope
   * @param {Object} data
   * @returns {Promise<Object|null>}
   */
  async saveScope(scope, data) {
    try {
      const res = await fetch(`/api/config/${scope}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to save ${scope} config: ${err.message}`, 'error');
      return null;
    }
  },

  /** @returns {Promise<Object|null>} */
  async getServiceStatus() {
    try {
      const res = await fetch('/api/services/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      Toast.show(`Failed to load service status: ${err.message}`, 'error');
      return null;
    }
  },

  /**
   * @param {'bot'|'agent'} service
   * @param {'start'|'stop'|'restart'} action
   * @returns {Promise<Object|null>}
   */
  async controlService(service, action) {
    try {
      const res = await fetch(`/api/services/${service}/${action}`, {
        method: 'POST',
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to ${action} ${service}: ${err.message}`, 'error');
      return null;
    }
  },

  /** @returns {Promise<Object|null>} */
  async getDriveStatus() {
    try {
      const res = await fetch('/api/drive/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      Toast.show(`Failed to load Drive status: ${err.message}`, 'error');
      return null;
    }
  },

  /** @returns {Promise<Object|null>} */
  async startDriveConnect() {
    try {
      const res = await fetch('/api/drive/connect/start', { method: 'POST' });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to start Drive connection: ${err.message}`, 'error');
      return null;
    }
  },
};
