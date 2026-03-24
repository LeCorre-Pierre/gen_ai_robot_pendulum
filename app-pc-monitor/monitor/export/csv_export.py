"""
CSV export for telemetry ring buffers.
"""

from __future__ import annotations

import csv
from pathlib import Path

from monitor.model.ring_buffer import RingBuffer
from monitor.model.telemetry import STREAM_DEFS


def export_streams(
    ring_buffers: dict[str, RingBuffer],
    path: str,
) -> int:
    """
    Write all signal buffers to a single CSV file.

    `ring_buffers` is a flat dict mapping signal names to RingBuffer instances.
    Signals are aligned by their sample index (not re-sampled).
    Returns the number of rows written.
    """
    if not ring_buffers:
        return 0

    # Use the signal with the most samples as the reference index
    max_count   = max(rb.count for rb in ring_buffers.values())
    if max_count == 0:
        return 0

    # Collect arrays
    all_times: dict[str, object] = {}
    all_vals:  dict[str, object] = {}
    for name, rb in ring_buffers.items():
        t, v = rb.get_arrays()
        all_times[name] = t
        all_vals[name]  = v

    signal_names = list(ring_buffers.keys())
    headers = ["sample"] + [f"time_{n}_s" for n in signal_names] + signal_names

    rows_written = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for i in range(max_count):
            row = [i]
            for name in signal_names:
                t = all_times[name]
                row.append(float(t[i]) if i < len(t) else "")
            for name in signal_names:
                v = all_vals[name]
                row.append(float(v[i]) if i < len(v) else "")
            writer.writerow(row)
            rows_written += 1

    return rows_written
