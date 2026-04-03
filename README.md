# Tacview Flight Path Importer for Blender

A Blender add-on that imports [Tacview](https://www.tacview.net/) CSV flight data and reconstructs aircraft flight paths as 3D animations.

![Blender](https://img.shields.io/badge/Blender-4.2_LTS-orange)
![License](https://img.shields.io/badge/License-MIT-blue)

## Features

- 📂 **CSV Import** — Read flight data exported from Tacview (CSV format)
- ✈️ **Multi-Aircraft Support** — Automatically detects and creates separate objects for each aircraft by ID
- 🎯 **Accurate Positioning** — Converts geographic coordinates (Lon/Lat/Alt) to local metric space, using the first data point as origin
- 🔄 **Smooth Attitude** — Full Roll / Pitch / Yaw reconstruction using quaternion interpolation (no gimbal lock)
- 🎬 **Keyframe Animation** — Generates Bézier-interpolated keyframes synced to scene or custom frame rate
- 🛤️ **Flight Path Curves** — Optional NURBS 3D curves visualizing the flight trail
- 🎨 **Auto Coloring** — Each aircraft gets a distinct color for easy identification

## Installation

1. Download `tacview_flight_path.py`
2. Open Blender → `Edit` → `Preferences` → `Add-ons` → `Install...`
3. Select the downloaded `.py` file and enable the add-on

## Usage

1. Export flight data as CSV from Tacview
2. In Blender, open the sidebar (`N`) → **Tacview** tab
3. Select your CSV file
4. Adjust settings if needed:
   - **Use Scene FPS** — Match Blender's frame rate, or set a custom value
   - **Arrow Size** — Scale of the aircraft arrow mesh (metres)
   - **Create Path Curve** — Toggle flight trail visualization
5. Click **Import Flight Path**
6. Play the animation (`Space`)

> **Tip:** Flight data spans large distances (kilometres). You may need to increase `View > Clip End` in the N-panel and press `Numpad .` to focus on the imported objects.

## CSV Format

The add-on expects Tacview's standard CSV export with at minimum these columns:

| Column | Description |
|--------|-------------|
| `ISO time` | Timestamp |
| `Id` | Aircraft identifier |
| `Longitude` | Geographic longitude |
| `Latitude` | Geographic latitude |
| `Altitude` | Altitude in metres |
| `Roll` | Bank angle (degrees) |
| `Pitch` | Nose up/down (degrees) |
| `Yaw` | Heading (degrees) |
| `Name` | Aircraft type (optional) |

## Coordinate System

- **Origin** — First data point becomes `(0, 0, 0)`
- **X axis** — East (longitude)
- **Y axis** — North (latitude)
- **Z axis** — Up (altitude)

## Requirements

- Blender **4.2 LTS** or later
- Tacview CSV export file

## License

MIT
