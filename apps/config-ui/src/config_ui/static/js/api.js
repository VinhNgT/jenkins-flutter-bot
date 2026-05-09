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

  /** @returns {Promise<Object|null>} */
  async getSchema() {
    try {
      const res = await fetch('/api/config/schema');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      Toast.show(`Failed to load schema: ${err.message}`, 'error');
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
        method: 'PUT',
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

  /** @returns {Promise<Object|null>} */
  async disconnectDrive() {
    try {
      const res = await fetch('/api/drive/token', { method: 'DELETE' });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to disconnect Drive: ${err.message}`, 'error');
      return null;
    }
  },

  /** @returns {Promise<{script: string, warnings: string[]}|null>} */
  async getJenkinsfile() {
    try {
      const res = await fetch('/api/jenkinsfile');
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to generate Jenkinsfile: ${err.message}`, 'error');
      return null;
    }
  },

  /** @returns {Promise<{env_content: string, warnings: string[]}|null>} */
  async getExportEnv() {
    try {
      const res = await fetch('/api/export/env');
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to generate .env: ${err.message}`, 'error');
      return null;
    }
  },

  /**
   * Download the OAuth token file. Returns true on success.
   * @returns {Promise<boolean>}
   */
  async downloadOAuth() {
    try {
      const res = await fetch('/api/export/oauth');
      if (!res.ok) {
        const result = await res.json();
        throw new Error(result.detail || `HTTP ${res.status}`);
      }
      // Trigger a browser download
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'oauth.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      return true;
    } catch (err) {
      Toast.show(`Failed to download oauth.json: ${err.message}`, 'error');
      return false;
    }
  },
};
