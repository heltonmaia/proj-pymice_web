"""Tests for filter_velocity_outliers helper.

Run from pymice/backend/:
    python test_outlier_filter.py
"""
import numpy as np

from app.routers.analysis import filter_velocity_outliers


def test_disabled_passes_through():
    v = np.array([1.0, 2.0, 3.0, 50.0, 4.0])
    t = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
    cleaned, mask = filter_velocity_outliers(v, t, k=3.0, enabled=False)
    assert np.array_equal(cleaned, v), f"expected unchanged, got {cleaned}"
    assert not mask.any(), f"expected no outliers flagged, got {mask}"


def test_single_spike_interpolated():
    # 9 values around ~2.0, with a single spike at index 4
    v = np.array([2.0, 2.1, 1.9, 2.0, 100.0, 2.0, 2.1, 1.9, 2.0])
    t = np.linspace(0.0, 0.8, 9)
    cleaned, mask = filter_velocity_outliers(v, t, k=3.0, enabled=True)
    assert mask[4], f"expected spike at idx 4 to be flagged; mask={mask}"
    assert mask.sum() == 1, f"only one outlier expected, got {mask.sum()}"
    # Interpolated value should be close to mean of neighbors (~2.0)
    assert abs(cleaned[4] - 2.0) < 0.2, f"expected ~2.0 after interp, got {cleaned[4]}"
    # Non-outlier values unchanged
    np.testing.assert_array_equal(cleaned[~mask], v[~mask])


def test_low_values_not_filtered():
    # Animal stationary (low velocities) — should NOT be flagged as outliers.
    v = np.array([5.0, 5.1, 4.9, 5.0, 0.01, 0.0, 0.02, 5.0, 5.1, 4.9])
    t = np.linspace(0.0, 0.9, 10)
    cleaned, mask = filter_velocity_outliers(v, t, k=3.0, enabled=True)
    assert not mask.any(), f"low values must not be flagged; mask={mask}"
    np.testing.assert_array_equal(cleaned, v)


def test_constant_signal_mad_zero():
    # All values identical → MAD == 0 → pass-through, no division by zero.
    v = np.array([2.0, 2.0, 2.0, 2.0, 2.0])
    t = np.linspace(0.0, 0.4, 5)
    cleaned, mask = filter_velocity_outliers(v, t, k=3.0, enabled=True)
    assert not mask.any()
    np.testing.assert_array_equal(cleaned, v)


def test_short_array_passthrough():
    # Fewer than 3 samples → cannot estimate; pass-through.
    v = np.array([1.0, 100.0])
    t = np.array([0.0, 0.1])
    cleaned, mask = filter_velocity_outliers(v, t, k=3.0, enabled=True)
    assert not mask.any()
    np.testing.assert_array_equal(cleaned, v)


def test_k_controls_sensitivity():
    # Same spike: a permissive k (large) must catch fewer outliers than strict (small).
    v = np.array([2.0, 2.1, 1.9, 2.0, 6.0, 2.0, 2.1, 1.9, 2.0])
    t = np.linspace(0.0, 0.8, 9)
    _, mask_strict = filter_velocity_outliers(v, t, k=3.0, enabled=True)
    _, mask_loose = filter_velocity_outliers(v, t, k=50.0, enabled=True)
    assert mask_strict[4], "strict k must flag the spike"
    assert not mask_loose[4], "loose k must not flag the same spike"


if __name__ == "__main__":
    tests = [
        test_disabled_passes_through,
        test_single_spike_interpolated,
        test_low_values_not_filtered,
        test_constant_signal_mad_zero,
        test_short_array_passthrough,
        test_k_controls_sensitivity,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    if failed:
        raise SystemExit(f"{failed} test(s) failed")
    print(f"\nAll {len(tests)} tests passed.")
