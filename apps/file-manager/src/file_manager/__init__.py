"""Backend-agnostic file storage service.

Provides a generic HTTP API for file upload, deletion, and lifecycle
management.  The current implementation uses Google Drive as the
storage backend, but the ``StorageBackend`` protocol allows swapping
in alternative providers (S3, local filesystem, etc.) without changing
the API contract.
"""
