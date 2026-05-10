"""
Custom PostgreSQL database backend with connection retry for Neon scale-to-zero.

Neon's free tier pauses the database after inactivity. The first request after
a pause can hit an OperationalError while Neon wakes up. This wrapper retries
the initial connection up to 3 times (2 s apart) before giving up.

Only the connection-establishment path is affected. Queries against an already-
open connection bypass this wrapper entirely (ensure_connection() returns
immediately when self.connection is not None).
"""

import logging
import time

from django.db import OperationalError
from django.db.backends.postgresql.base import DatabaseWrapper as PostgresDatabaseWrapper

logger = logging.getLogger(__name__)

# PostgreSQL SQLSTATE class '08' = connection_exception family.
# psycopg2 also raises OperationalError for pure socket failures (refused,
# timeout, DNS), in which case pgcode is None — those should also be retried.
_CONNECTION_PGCODE_PREFIX = '08'

_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds


def _is_connection_error(exc: OperationalError) -> bool:
    """Return True if exc looks like a transient connection failure."""
    cause = getattr(exc, '__cause__', None)
    if cause is None:
        # Wrapped without an underlying psycopg2 cause — treat as connection error.
        return True
    pgcode = getattr(cause, 'pgcode', None)
    # pgcode is None  → socket-level failure (connection refused, timeout, …)
    # pgcode starts with '08' → PostgreSQL connection_exception class
    return pgcode is None or pgcode.startswith(_CONNECTION_PGCODE_PREFIX)


class DatabaseWrapper(PostgresDatabaseWrapper):
    """PostgreSQL backend that retries connection establishment on failure."""

    def ensure_connection(self):
        if self.connection is not None:
            # Already connected — skip retry logic entirely.
            return super().ensure_connection()

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                super().ensure_connection()
                return
            except OperationalError as exc:
                if not _is_connection_error(exc) or attempt == _MAX_RETRIES:
                    raise
                logger.warning(
                    'DB connection attempt %d/%d failed (Neon waking up?), '
                    'retrying in %ds — %s',
                    attempt, _MAX_RETRIES, _RETRY_DELAY, exc,
                )
                time.sleep(_RETRY_DELAY)
