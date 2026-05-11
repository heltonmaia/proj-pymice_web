# Velocity Outlier Filter — Design

**Date:** 2026-05-11
**Area:** Ethological Analysis tab → Velocity Analysis
**Files touched:**
- `pymice/backend/app/routers/analysis.py`
- `pymice/backend/app/models/schemas.py`
- `pymice/frontend/src/types/index.ts`
- `pymice/frontend/src/pages/EthologicalTab.tsx`

## Problem

Tracking glitches (centroid jumping for a single frame) produce isolated spikes in the per-frame velocity series `v = dist / dt`. Today these spikes:

- Distort the **Velocity Over Time** line plot — the moving-average smoothing smears them across `window` frames rather than removing them.
- Inflate **Mean / Max Velocity** in the statistics panel and **Total Distance** (Max Velocity can read 5000+ px/s from a single bad frame).
- Skew the **Activity histogram**, partially mitigated today by a hard 99th-percentile clip used only for the histogram display.

There is no real-velocity filter anywhere in the pipeline.

## Goal

Add a robust outlier filter to the velocity series so spikes are removed before plotting, statistics, and histogram. Applied at the analysis step only — raw tracking data (centroids in the JSON export) is **not** modified.

## Algorithm — Median + k·MAD with linear interpolation

Robust filter (own outliers do not inflate the threshold) using Median Absolute Deviation:

```python
def filter_velocity_outliers(velocities, time_points, k=3.0, enabled=True):
    """
    Returns (cleaned_velocities, outlier_mask).
    Filters only the upper tail (spikes); low/zero velocities are real signal.
    """
    if not enabled or len(velocities) < 3:
        return velocities, np.zeros_like(velocities, dtype=bool)

    med = np.median(velocities)
    mad = np.median(np.abs(velocities - med))
    if mad == 0:
        return velocities, np.zeros_like(velocities, dtype=bool)

    # 1.4826 makes k interpretable as "k standard deviations" for normal data
    threshold = med + k * 1.4826 * mad
    mask = velocities > threshold   # upper tail only

    if mask.all():
        return velocities, mask

    cleaned = np.interp(time_points, time_points[~mask], velocities[~mask])
    return cleaned, mask
```

**Design choices:**
- **MAD over std:** the spike itself is the problem, so any estimator that uses the spike to set its own threshold (mean + k·std) is self-defeating.
- **Upper tail only:** a stationary animal is real information; filtering low velocities would hide rest periods.
- **Linear interpolation between non-outlier neighbors:** keeps the time axis continuous, no gaps in the plot, and the smoothing/statistics work on a full array. `np.interp` handles the edges by extending the nearest non-outlier value.
- **Two safety fallbacks:** `MAD == 0` (constant velocities) and `mask.all()` (degenerate) both return the original array — feature degrades to no-op rather than failing.

## Backend integration

Helper goes at module scope in `pymice/backend/app/routers/analysis.py`. Three call sites, all immediately after the existing per-frame velocity computation:

| Function | Current line ref | What changes |
|---|---|---|
| `analyze_movement` | ~253 | After building `velocities`, replace with `cleaned`; recompute `total_distance = np.sum(cleaned * dt)`; stats text uses `cleaned`. |
| `generate_complete_analysis` | ~481 | Same: replace `velocities` with `cleaned` before moving-average, `movement_threshold` percentile, histogram, activity classification. |
| `download_complete_analysis` | ~644 (approx.) | Same as above. |

**`total_distance` is recomputed from cleaned velocities** (`Σ cleaned · dt`) instead of summing raw `dist_consecutive` — this is the user-confirmed semantics: if a frame is an outlier, the distance attributed to that frame is the interpolated value, not the spike.

The histogram's existing 99th-percentile display clip stays — with the cleaned series, it becomes a no-op in most cases but remains a safety net for very long tails on legitimate data.

## Schema

`HeatmapSettings` (in `pymice/backend/app/models/schemas.py`) gains two fields:

```python
outlier_filter_enabled: bool = True
outlier_filter_k: float = Field(default=3.0, ge=1.0, le=10.0)
```

Defaults chosen to make the filter **active out of the box** at a standard robust-stats threshold (k=3 ≈ 3σ for normal data).

Frontend `HeatmapSettings` in `pymice/frontend/src/types/index.ts` gets the same fields as optional:

```ts
outlier_filter_enabled?: boolean;
outlier_filter_k?: number;
```

Defaults in the frontend state initializers (two locations in `EthologicalTab.tsx`, lines ~21 and ~59) are set to `true` / `3.0`.

## UI

Inside the existing **Velocity Analysis** card in `EthologicalTab.tsx` (around line 1262), below the Smoothing Window slider:

- **Checkbox:** *"Outlier Filter (Median + k·MAD)"* — default checked.
- **Slider:** *"Threshold: k = X.X"*, range `1.0–10.0`, step `0.5`, default `3.0`. Disabled (greyed) when the checkbox is off.
- **Helper text** (small, muted): *"Removes spikes from tracking glitches"*.

Styled to match the existing Smoothing Window slider — same Tailwind utility patterns, same dark-mode classes.

State flows through `heatmapSettings.outlier_filter_enabled` / `heatmapSettings.outlier_filter_k`, which is already serialized into the analysis API payload via the existing `settings` field — no change to the API client (`services/api.ts`).

## Out of scope

- **Reporting the outlier count** (e.g., "3 outliers removed") in the UI or stats panel. Useful for diagnostics but would require adding a return field to the analysis response and rendering it; deferred.
- **Refactoring the three duplicated velocity-calculation blocks** into a single shared function. Tempting but unrelated to this fix.
- **Filtering centroids/JSON results.** This change is purely post-processing for analysis output.
- **Different filters per endpoint.** All three endpoints get the same filter with the same settings.

## Testing approach

- Manual: load a tracking result known to contain a glitch frame, verify the spike disappears from the Velocity plot, Max Velocity in stats drops to a plausible value, and toggling the checkbox restores the spike.
- Unit-test target: `filter_velocity_outliers` — cases: no outliers (pass-through), single spike (replaced by interpolation), `MAD == 0` (pass-through), all-outliers degenerate (pass-through), `enabled=False` (pass-through), upper-only (low values not touched).
