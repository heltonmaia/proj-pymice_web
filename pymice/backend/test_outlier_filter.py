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


def test_zero_inflated_with_spike():
    # Real-world case: mouse stationary >50% of frames (velocity == 0),
    # bulk movement ~10 px/s, occasional spike at 1000 px/s.
    # Median and MAD both collapse to 0; filter must still catch the spike.
    rng = np.random.default_rng(0)
    N = 1000
    v = np.zeros(N)
    move_idx = rng.choice(N, size=N // 3, replace=False)  # 33% active frames
    v[move_idx] = rng.uniform(5.0, 15.0, size=len(move_idx))
    spike_idx = [100, 500, 800]
    v[spike_idx] = 1000.0
    t = np.linspace(0.0, N / 30.0, N)

    cleaned, mask = filter_velocity_outliers(v, t, k=3.0, enabled=True)
    for i in spike_idx:
        assert mask[i], f"spike at idx {i} must be flagged (zero-inflated case)"
    assert cleaned.max() < 100.0, f"cleaned max too high: {cleaned.max()}"


def test_quantized_movement_with_spike():
    # Matches the real user data shape (logged: med=30.12 mad=0.22).
    # Heavy quantization: >95% of moving frames sit exactly on the 30 px/s
    # quantum (1 px/frame at 30 fps with integer-pixel detection).
    # Only ~5% of moving frames carry real spread up to ~200 px/s.
    # MAD collapses to near zero, so the old algorithm clips at ~30 px/s.
    # The new algorithm must use a percentile-based scale and preserve real
    # movement while catching the tracking-glitch spikes.
    rng = np.random.default_rng(42)
    N = 5000
    v = np.zeros(N)
    # 30% of frames are moving (matches typical mostly-stationary recording);
    # this puts >50% of all velocities at exactly zero so median(all)==0.
    move_idx = rng.choice(N, size=int(N * 0.30), replace=False)
    quantum_mask = rng.random(len(move_idx)) < 0.95
    v[move_idx[quantum_mask]] = 30.0
    other = move_idx[~quantum_mask]
    v[other] = rng.uniform(30.0, 200.0, size=len(other))
    spike_idx = [500, 1500, 3000, 4200]
    v[spike_idx] = 6000.0
    t = np.linspace(0.0, N / 30.0, N)

    cleaned, mask = filter_velocity_outliers(v, t, k=3.0, enabled=True)
    for i in spike_idx:
        assert mask[i], f"spike at idx {i} must be flagged"
    assert cleaned.max() < 500.0, f"cleaned max suggests spikes survived: {cleaned.max()}"
    assert cleaned.max() > 100.0, (
        f"cleaned max too aggressive — legit movement was clipped: {cleaned.max()}"
    )


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
        test_zero_inflated_with_spike,
        test_quantized_movement_with_spike,
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
