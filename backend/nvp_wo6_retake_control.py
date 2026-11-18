"""Private single-operation cancellation handle for the trusted desktop.

Never accepts a browser task ID or a worker process handle. The existing
execution owner installs the exact durable cancellation fence after admission.
"""
from threading import RLock

from backend.nvp_wo6_recovery import RetakeRecovery


class RetakeControl:
    def __init__(self):
        self._lock = RLock()
        self._recovery = None
        self._task_id = None
        self._closed = False

    @property
    def task_id(self):
        with self._lock:
            return self._task_id

    def bind(self, recovery, task_id):
        if not isinstance(recovery, RetakeRecovery):
            raise TypeError("Existing native recovery owner required")
        with self._lock:
            if self._closed or self._task_id is not None:
                raise PermissionError("Take operation handle already used")
            recovery._held()
            recovery.cancelled(task_id)  # prove exact active lifecycle binding
            self._recovery, self._task_id = recovery, task_id

    def request(self):
        with self._lock:
            if self._closed:
                return "NOT_ACTIVE"
            if self._recovery is None:
                return "NOT_READY"
            try:
                accepted = self._recovery.request_cancel(self._task_id)
            except PermissionError:
                row = self._recovery.ledger.get_task(self._task_id)
                if row is not None and row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"):
                    return "TOO_LATE"
                raise
            return "CANCELLATION_REQUESTED" if accepted else "TOO_LATE"

    def close(self):
        # Serialize with a concurrently running cancellation before the
        # execution owner releases its native kernel lease.
        with self._lock:
            self._closed = True
            self._recovery = None
