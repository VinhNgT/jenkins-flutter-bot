/* Centralized API client — all fetch calls go through here. */

import { Toast } from './toast.js';

export const API = {
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
   * @param {'bot'|'agent'|'builds'|'file_manager'} scope
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
   * @param {'bot'|'agent'|'builds'|'file_manager'} service
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

  /**
   * @param {Object} [opts={}]
   * @returns {Promise<{script_public: string, script_private: string, warnings: string[]}|null>}
   */
  async getJenkinsfile(opts = {}) {
    try {
      const params = new URLSearchParams(opts).toString();
      const url = params ? `/api/jenkinsfile?${params}` : '/api/jenkinsfile';
      const res = await fetch(url);
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to generate Jenkinsfile: ${err.message}`, 'error');
      return null;
    }
  },

  /** @returns {Promise<{files: Object, compose_vars: Object, warnings: string[]}|null>} */
  async getExportEnv() {
    try {
      const res = await fetch('/api/export/env');
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to generate env: ${err.message}`, 'error');
      return null;
    }
  },

  /**
   * Download the config tarball. Returns true on success.
   * @returns {Promise<boolean>}
   */
  async downloadTarball() {
    try {
      const res = await fetch('/api/export/tarball');
      if (!res.ok) {
        const result = await res.json();
        throw new Error(result.detail || `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'jfb-config.tar.gz';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      return true;
    } catch (err) {
      Toast.show(`Failed to download tarball: ${err.message}`, 'error');
      return false;
    }
  },

  /**
   * Import a config tarball.
   * @param {File} file
   * @returns {Promise<Object|null>}
   */
  async importTarball(file) {
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/api/import/tarball', {
        method: 'POST',
        body: form,
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || `HTTP ${res.status}`);
      return result;
    } catch (err) {
      Toast.show(`Failed to import config: ${err.message}`, 'error');
      return null;
    }
  },
};
