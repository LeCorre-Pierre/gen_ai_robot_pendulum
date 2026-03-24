"""
Unit tests for monitor.model.ring_buffer.RingBuffer
"""

import numpy as np
import pytest

from monitor.model.ring_buffer import RingBuffer


class TestRingBufferBasics:
    def test_initial_count_zero(self):
        rb = RingBuffer(100)
        assert rb.count == 0

    def test_capacity_property(self):
        rb = RingBuffer(256)
        assert rb.capacity == 256

    def test_capacity_too_small_raises(self):
        with pytest.raises(ValueError):
            RingBuffer(1)

    def test_push_increments_count(self):
        rb = RingBuffer(10)
        rb.push(0.0, 1.0)
        assert rb.count == 1
        rb.push(1.0, 2.0)
        assert rb.count == 2

    def test_count_capped_at_capacity(self):
        cap = 8
        rb  = RingBuffer(cap)
        for i in range(cap + 10):
            rb.push(float(i), float(i))
        assert rb.count == cap

    def test_get_arrays_empty(self):
        rb = RingBuffer(10)
        t, v = rb.get_arrays()
        assert len(t) == 0
        assert len(v) == 0

    def test_get_arrays_partial(self):
        rb = RingBuffer(100)
        for i in range(5):
            rb.push(float(i), float(i * 2))
        t, v = rb.get_arrays()
        assert len(t) == 5
        assert len(v) == 5
        np.testing.assert_array_equal(t, [0., 1., 2., 3., 4.])
        np.testing.assert_array_equal(v, [0., 2., 4., 6., 8.])

    def test_clear_resets_count(self):
        rb = RingBuffer(10)
        for i in range(5):
            rb.push(float(i), float(i))
        rb.clear()
        assert rb.count == 0
        t, v = rb.get_arrays()
        assert len(t) == 0


class TestRingBufferOverwrite:
    def test_oldest_overwritten(self):
        rb = RingBuffer(4)
        for i in range(6):
            rb.push(float(i), float(i))
        # Only last 4 values remain (2,3,4,5)
        t, v = rb.get_arrays()
        assert len(t) == 4
        assert len(v) == 4
        # Values must be sorted (chronological)
        assert list(t) == [2.0, 3.0, 4.0, 5.0]
        assert list(v) == [2.0, 3.0, 4.0, 5.0]

    def test_wrap_order_correct(self):
        cap = 5
        rb  = RingBuffer(cap)
        for i in range(12):
            rb.push(float(i), float(i))
        t, v = rb.get_arrays()
        # should be 7,8,9,10,11 in order
        expected = list(range(12 - cap, 12))
        assert list(t) == [float(x) for x in expected]
        assert list(v) == [float(x) for x in expected]

    def test_exactly_full_no_overwrite_yet(self):
        rb = RingBuffer(4)
        for i in range(4):
            rb.push(float(i), float(i * 10))
        t, v = rb.get_arrays()
        assert list(t) == [0., 1., 2., 3.]
        assert list(v) == [0., 10., 20., 30.]


class TestRingBufferPushBulk:
    def test_push_bulk_small(self):
        rb = RingBuffer(10)
        ts = np.array([1.0, 2.0, 3.0])
        vs = np.array([10.0, 20.0, 30.0])
        rb.push_bulk(ts, vs)
        t, v = rb.get_arrays()
        np.testing.assert_array_equal(t, ts)
        np.testing.assert_array_equal(v, vs)

    def test_push_bulk_overflow(self):
        rb = RingBuffer(4)
        ts = np.arange(10, dtype=float)
        vs = np.arange(10, dtype=float)
        rb.push_bulk(ts, vs)
        t, v = rb.get_arrays()
        assert len(t) == 4
        # Only last 4 values should remain
        np.testing.assert_array_equal(t, [6., 7., 8., 9.])

    def test_push_bulk_wraps(self):
        rb = RingBuffer(5)
        # Fill 3 first
        rb.push_bulk(np.array([0., 1., 2.]), np.array([0., 1., 2.]))
        # Add 4 more (wraps)
        rb.push_bulk(np.array([3., 4., 5., 6.]), np.array([3., 4., 5., 6.]))
        t, v = rb.get_arrays()
        assert len(t) == 5
        np.testing.assert_array_equal(t, [2., 3., 4., 5., 6.])

    def test_push_bulk_empty_noop(self):
        rb = RingBuffer(10)
        rb.push_bulk(np.array([]), np.array([]))
        assert rb.count == 0

    def test_push_bulk_matches_individual_pushes(self):
        cap = 20
        rb1 = RingBuffer(cap)
        rb2 = RingBuffer(cap)
        ts = np.arange(15, dtype=float)
        vs = np.arange(15, dtype=float) * 0.5
        for t, v in zip(ts, vs):
            rb1.push(t, v)
        rb2.push_bulk(ts, vs)
        t1, v1 = rb1.get_arrays()
        t2, v2 = rb2.get_arrays()
        np.testing.assert_allclose(t1, t2)
        np.testing.assert_allclose(v1, v2)


class TestRingBufferDataIntegrity:
    def test_timestamps_monotonic_after_wrap(self):
        rb = RingBuffer(8)
        for i in range(20):
            rb.push(float(i), float(i))
        t, _ = rb.get_arrays()
        diffs = np.diff(t)
        assert np.all(diffs > 0), "timestamps not monotonically increasing"

    def test_large_capacity(self):
        rb = RingBuffer(10_000)
        for i in range(10_000):
            rb.push(float(i), float(i))
        t, v = rb.get_arrays()
        assert len(t) == 10_000
        assert t[0] == 0.0
        assert t[-1] == 9999.0

    def test_float_values_preserved(self):
        rb = RingBuffer(10)
        rb.push(0.1, 3.14159265)
        _, v = rb.get_arrays()
        assert abs(v[0] - 3.14159265) < 1e-10

    def test_negative_values(self):
        rb = RingBuffer(10)
        rb.push(1.0, -42.5)
        _, v = rb.get_arrays()
        assert v[0] == -42.5
