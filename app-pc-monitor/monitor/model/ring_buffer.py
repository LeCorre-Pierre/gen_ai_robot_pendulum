"""
Fixed-capacity numpy ring buffer for a (timestamp, value) signal pair.

Designed for single-producer / single-consumer from the Qt main thread only.
No locking needed.
"""

from __future__ import annotations

import numpy as np


class RingBuffer:
    """
    Stores up to `capacity` (time, value) float32 pairs.
    When full, the oldest sample is overwritten.
    """

    def __init__(self, capacity: int = 10_000) -> None:
        if capacity < 2:
            raise ValueError("capacity must be >= 2")
        self._cap   = capacity
        self._times = np.empty(capacity, dtype=np.float64)
        self._vals  = np.empty(capacity, dtype=np.float64)
        self._head  = 0   # index of next write
        self._count = 0   # number of valid samples

    # ── Write ────────────────────────────────────────────────────────────────
    def push(self, timestamp: float, value: float) -> None:
        self._times[self._head] = timestamp
        self._vals[self._head]  = value
        self._head = (self._head + 1) % self._cap
        if self._count < self._cap:
            self._count += 1

    def push_bulk(self, timestamps: np.ndarray, values: np.ndarray) -> None:
        """Push multiple samples at once (faster than looping push())."""
        n = len(timestamps)
        if n == 0:
            return
        if n >= self._cap:
            # Only keep the last `_cap` samples
            timestamps = timestamps[-self._cap:]
            values     = values[-self._cap:]
            n          = self._cap

        end = (self._head + n) % self._cap
        if end > self._head:
            self._times[self._head:end] = timestamps
            self._vals[self._head:end]  = values
        else:
            first_chunk = self._cap - self._head
            self._times[self._head:] = timestamps[:first_chunk]
            self._vals[self._head:]  = values[:first_chunk]
            self._times[:end]        = timestamps[first_chunk:]
            self._vals[:end]         = values[first_chunk:]

        self._head  = end
        self._count = min(self._count + n, self._cap)

    # ── Read ─────────────────────────────────────────────────────────────────
    def get_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Return (times, values) in chronological order.
        Returns views / copies suitable for pyqtgraph.
        """
        if self._count == 0:
            empty = np.empty(0, dtype=np.float64)
            return empty, empty.copy()

        if self._count < self._cap:
            return (self._times[:self._count].copy(),
                    self._vals[:self._count].copy())

        # Buffer is full: unwrap from head
        idx = np.arange(self._cap)
        order = (self._head + idx) % self._cap
        return self._times[order].copy(), self._vals[order].copy()

    @property
    def count(self) -> int:
        return self._count

    @property
    def capacity(self) -> int:
        return self._cap

    def clear(self) -> None:
        self._head  = 0
        self._count = 0
