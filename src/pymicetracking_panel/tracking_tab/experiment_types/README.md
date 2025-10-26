# Experiment Types - ROI Presets

This directory stores saved ROI configurations that can be reused across different experiments.

## File Format

Each preset is stored as a JSON file with the following structure:

```json
{
  "preset_name": "my_experiment_setup",
  "description": "Custom ROI configuration",
  "timestamp": "2025-10-12T19:45:00",
  "rois": [
    {
      "center_x": 320,
      "center_y": 240,
      "width": 200,
      "height": 150,
      "roi_type": "Rectangle"
    }
  ]
}
```

## Usage

1. **Save a preset**: Draw your ROIs in the tracking tab, then click "Save ROI" and enter a name
2. **Load a preset**: Select the preset name from the "Experiment Type" dropdown
3. **Reuse configurations**: Use the same ROI setup across multiple video analyses

## Default Experiment Types

The dropdown "Experiment Type" shows two default types:
- **EPM** - Elevated Plus Maze (for metadata only, no preset ROIs)
- **OF** - Open Field (for metadata only, no preset ROIs)

All custom ROI configurations are saved as presets in this directory and appear below a separator in the dropdown.
