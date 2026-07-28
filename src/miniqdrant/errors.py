from __future__ import annotations


class MiniQdrantError(Exception):
    """Base class for public MiniQdrant errors."""


class CollectionExistsError(MiniQdrantError):
    """Raised when creating a collection that already exists."""


class CollectionNotFoundError(MiniQdrantError):
    """Raised when a collection cannot be found."""


class SchemaMismatchError(MiniQdrantError):
    """Raised when persisted and requested collection schemas differ."""


class InvalidPointError(MiniQdrantError, ValueError):
    """Raised when a point identifier or payload is invalid."""


class InvalidVectorError(InvalidPointError):
    """Raised when a vector violates its collection contract."""


class InvalidFilterError(MiniQdrantError, ValueError):
    """Raised when a payload filter is malformed."""


class PayloadIndexError(MiniQdrantError):
    """Raised when a payload index operation is invalid."""


class CorruptionError(MiniQdrantError):
    """Raised when durable data fails structural or checksum validation."""


class ClosedResourceError(MiniQdrantError):
    """Raised when work is submitted to a closed resource."""


class SnapshotError(MiniQdrantError):
    """Raised when snapshot creation or restore cannot complete safely."""

