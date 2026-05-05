# dji-flightlog-parser

Enterprise-grade DJI flight log parser and decryptor for version 13 and 14 log files. Decrypts, parses, and exports DJI flight telemetry to JSON, GeoJSON, KML, and CSV.

## Features

- Full decryption of v13/v14 DJI flight logs via the DJI OpenAPI keychains endpoint
- CRC64-based XOR decoding and AES-256-CBC decryption with IV chaining
- Comprehensive record parsing: OSD, Home, Gimbal, RC, Battery, Camera, GPS, IMU, OFDM, Vision/Perception, Navigation, and more
- ADS-B / DJI AirSense support: nearby manned aircraft with ICAO address, position, altitude, and heading
- Battery health data: cycle count, designed capacity, component serial numbers
- Vision system state: collision avoidance, braking, ascent limiting
- Flight controller estimates: remaining flight time, battery reserves for landing/go-home
- Controller/app GPS position with horizontal accuracy
- Component serial numbers and firmware versions in flight summary
- Frame aggregation into normalized ~10 Hz telemetry frames
- JSON output compatible with the Rust `dji-log-parser` (drop-in replacement)
- GeoJSON, KML, and CSV export
- Keychain response caching for repeated parsing
- CLI with the same interface as the Rust `dji-log-parser` tool

## Extracted Data Reference

Every frame (emitted at ~10 Hz) contains the following data groups. The summary is emitted once per flight.

### Summary (per flight)

| Field | Type | Description |
|---|---|---|
| `startTime` | string | Flight start time (ISO 8601 UTC) |
| `startCoordinate` | object | `{ latitude, longitude }` of takeoff point |
| `totalTime` | float | Total flight duration (seconds) |
| `totalDistance` | float | Total distance traveled (km) |
| `maxHeight` | float | Maximum height above takeoff (meters) |
| `maxHorizontalSpeed` | float | Maximum horizontal speed (m/s) |
| `maxVerticalSpeed` | float | Maximum vertical speed (m/s) |
| `aircraftName` | string | Aircraft model name (e.g. "Matrice 4TD") |
| `aircraftSn` | string | Aircraft serial number |
| `cameraSn` | string | Camera serial number |
| `rcSn` | string | Remote controller serial number |
| `batterySn` | string | Battery serial number |
| `appPlatform` | string | Controller app platform ("Android" / "iOS") |
| `appVersion` | string | Controller app version |
| `productType` | string | DJI product type identifier |
| `componentSerials` | object | Map of component name to serial (e.g. `{ "RightCamera": "..." }`) |
| `firmwareVersions` | array | `[{ senderType, subSenderType, version }]` for each module |
| `batteryCycleCount` | int | Battery charge cycle count |
| `batteryDesignedCapacity` | int | Factory designed capacity (mAh) |
| `batterySerial` | string | Battery serial (when available from SmartBattery records) |

### OSD — On-Screen Display / Flight Telemetry

| Field | Type | Description |
|---|---|---|
| `flyTime` | float | Time since motors started (seconds) |
| `latitude` | float | Drone latitude (degrees) |
| `longitude` | float | Drone longitude (degrees) |
| `height` | float | Height above takeoff point (meters) |
| `heightMax` | float | Max height reached this flight (meters) |
| `vpsHeight` | float | Visual Positioning System height (meters) |
| `altitude` | float | Altitude above sea level (meters, home altitude + height) |
| `xSpeed` / `ySpeed` / `zSpeed` | float | Speed in body axes (m/s) |
| `xSpeedMax` / `ySpeedMax` / `zSpeedMax` | float | Max speed reached in each axis (m/s) |
| `pitch` / `roll` / `yaw` | float | Aircraft attitude (degrees) |
| `flycState` | string | Flight controller mode (e.g. "GPSAtti", "Waypoint", "GoHome") |
| `flycCommand` | string | Active command from app |
| `flightAction` | string | Current flight action |
| `isGpdUsed` | bool | Whether GPS is used for positioning |
| `nonGpsCause` | string | Reason GPS is not used |
| `gpsNum` | int | Number of GPS satellites |
| `gpsLevel` | int | GPS signal level (0–5) |
| `droneType` | string | Drone type identifier |
| `goHomeStatus` | string | Go-home state ("Standby", "GoingHome", etc.) |
| `batteryType` | string | Battery type ("Smart", "NonSmart") |
| `isOnGround` | bool | Whether the drone is on the ground |
| `isMotorOn` | bool | Whether motors are spinning |
| `isMotorBlocked` | bool | Motor blocked flag |
| `motorStartFailedCause` | string | Reason motor failed to start |
| `isImuPreheated` | bool | IMU preheat status |
| `imuInitFailReason` | string | IMU initialization failure reason |
| `isAcceletorOverRange` | bool | Accelerometer over range |
| `isBarometerDeadInAir` | bool | Barometer failure in flight |
| `isCompassError` | bool | Compass error |
| `isGoHomeHeightModified` | bool | Go-home height modified flag |
| `isNotEnoughForce` | bool | Insufficient thrust |
| `isOutOfLimit` | bool | Flight boundary reached |
| `isPropellerCatapult` | bool | Propeller catapult detected |
| `isVibrating` | bool | Abnormal vibration detected |
| `isVisionUsed` | bool | Vision system active for positioning |
| `voltageWarning` | int | Battery voltage warning level (0 = none) |

### Gimbal

| Field | Type | Description |
|---|---|---|
| `mode` | string | Gimbal mode ("YawFollow", "Free", etc.) |
| `pitch` / `roll` / `yaw` | float | Gimbal angles (degrees) |
| `isPitchAtLimit` | bool | Pitch axis at mechanical limit |
| `isRollAtLimit` | bool | Roll axis at mechanical limit |
| `isYawAtLimit` | bool | Yaw axis at mechanical limit |
| `isStuck` | bool | Gimbal stuck |

### Camera

| Field | Type | Description |
|---|---|---|
| `isPhoto` | bool | Photo shutter triggered this frame |
| `isVideo` | bool | Video recording active |
| `sdCardIsInserted` | bool | SD card present |
| `sdCardState` | string | SD card state |

### RC — Remote Controller

| Field | Type | Description |
|---|---|---|
| `aileron` | int | Right stick horizontal (roll) |
| `elevator` | int | Right stick vertical (pitch) |
| `throttle` | int | Left stick vertical |
| `rudder` | int | Left stick horizontal (yaw) |
| `downlinkSignal` | int | Video downlink signal strength (%) |
| `uplinkSignal` | int | Control uplink signal strength (%) |

### Battery

| Field | Type | Description |
|---|---|---|
| `chargeLevel` | int | Current charge level (%) |
| `voltage` | float | Total battery voltage (V) |
| `current` | float | Discharge current (A) |
| `currentCapacity` | int | Remaining capacity (mAh) |
| `fullCapacity` | int | Full charge capacity (mAh) |
| `cellNum` | int | Number of cells |
| `cellVoltages` | array | Per-cell voltages (V) |
| `isCellVoltageEstimated` | bool | True if cell voltages are computed from total voltage |
| `cellVoltageDeviation` | float | Max-min cell voltage difference (V) |
| `maxCellVoltageDeviation` | float | Highest cell deviation during flight (V) |
| `temperature` | float | Battery temperature (°C) |
| `minTemperature` / `maxTemperature` | float | Temperature range during flight (°C) |
| `cycleCount` | int | Charge cycle count |
| `designedCapacity` | int | Factory designed capacity (mAh) |
| `batterySerial` | string | Battery serial number |

### Home — Home Point and Flight Limits

| Field | Type | Description |
|---|---|---|
| `latitude` / `longitude` | float | Home point coordinates |
| `altitude` | float | Home point altitude (meters ASL) |
| `heightLimit` | float | Maximum allowed height (meters) |
| `isHomeRecord` | bool | Whether this is a valid home point record |
| `goHomeMode` | string | Go-home mode |
| `isDynamicHomePointEnabled` | bool | Dynamic home point tracking active |
| `isNearDistanceLimit` | bool | Near max distance from home |
| `isNearHeightLimit` | bool | Near max height limit |
| `isCompassCalibrating` | bool | Compass calibration in progress |
| `compassCalibrationState` | string | Calibration state |
| `isBeginnerMode` | bool | Beginner mode active |
| `goHomeHeight` | int | Go-home altitude (meters) |
| `maxAllowedHeight` | float | Regulatory max height (meters) |

### App GPS — Controller/Phone Position

| Field | Type | Description |
|---|---|---|
| `latitude` / `longitude` | float | Controller/phone GPS position (degrees) |
| `horizontalAccuracy` | float | GPS horizontal accuracy (meters) |

### Vision — Obstacle Avoidance State

| Field | Type | Description |
|---|---|---|
| `collisionAvoidanceEnabled` | bool | Collision avoidance system active |
| `isBraking` | bool | Drone is braking due to obstacle |
| `isAscentLimited` | bool | Ascent limited by obstacle above |
| `isLandingConfirmationNeeded` | bool | Landing confirmation needed (obstacle below) |

### Flight Controller — Battery and Time Estimates

| Field | Type | Description |
|---|---|---|
| `remainingFlightTime` | int | Estimated remaining flight time (seconds) |
| `batteryPercentNeededToLand` | int | Battery % needed to land at current position |
| `batteryPercentNeededToGoHome` | int | Battery % needed to return to home point and land |

### Nearby Aircraft — ADS-B / DJI AirSense

Array of detected manned aircraft (empty when none are nearby).

| Field | Type | Description |
|---|---|---|
| `icaoAddress` | string | ICAO 24-bit transponder address (hex, e.g. "47875a") |
| `latitude` / `longitude` | float | Aircraft position (degrees) |
| `altitude` | int | Barometric altitude (feet) |
| `heading` | float | Track heading (degrees, 0–360) |

### Recover — Device Identity

| Field | Type | Description |
|---|---|---|
| `appPlatform` | string | App platform |
| `appVersion` | string | App version |
| `aircraftName` | string | Aircraft model name |
| `aircraftSn` | string | Aircraft serial number |
| `cameraSn` | string | Camera serial number |
| `rcSn` | string | Remote controller serial number |
| `batterySn` | string | Battery serial number |

### App Messages

| Field | Type | Description |
|---|---|---|
| `tip` | string | Informational messages (flight mode changes, gimbal events) |
| `warn` | string | Warning messages (app warnings, serious warnings) |

## Installation

### From source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### With development dependencies

```bash
pip install -e ".[dev]"
```

## Usage

### CLI

```bash
# Basic parse (JSON to stdout)
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY

# Write JSON to file
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY --output result.json

# Raw records instead of aggregated frames
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY --raw --output raw.json

# Export GeoJSON
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY --geojson track.geojson

# Export KML
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY --kml track.kml

# Export CSV
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY --csv telemetry.csv

# Verbose logging
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY -v
```

### Python API

```python
from dji_flightlog_parser import DJILog

log = DJILog.from_file("flight.txt")
keychains = log.fetch_keychains("YOUR_DJI_API_KEY")

# Aggregated frames (10 Hz normalized telemetry)
frames = log.frames(keychains)

# Raw parsed records
records = log.records(keychains)

# Flight metadata
print(log.details.aircraft_name)
print(log.details.product_type)
```

### Export programmatically

```python
from dji_flightlog_parser.export.json_export import export_json
from dji_flightlog_parser.export.geojson import export_geojson
from dji_flightlog_parser.export.kml import export_kml
from dji_flightlog_parser.export.csv_export import export_csv

json_str = export_json(log.version, log.details, frames)
geojson_str = export_geojson(log.details, frames)
kml_str = export_kml(log.details, frames)
csv_str = export_csv(frames)
```

## Docker

### Build

```bash
docker build -t dji-flightlog-parser .
```

### Run

```bash
# Parse a file (mount as volume)
docker run --rm \
  -v /path/to/logs:/data \
  dji-flightlog-parser \
  /data/flight.txt --api-key YOUR_DJI_API_KEY --output /data/result.json

# Parse with raw output
docker run --rm \
  -v /path/to/logs:/data \
  dji-flightlog-parser \
  /data/flight.txt --api-key YOUR_DJI_API_KEY --raw --output /data/raw.json
```

### Run tests

```bash
docker build --target test -t dji-flightlog-parser-test .
docker run --rm \
  -v /path/to/example_files:/app/example_files \
  -e app_key=YOUR_DJI_API_KEY \
  dji-flightlog-parser-test
```

## Loggflyt Integration

This parser is a drop-in replacement for the Rust `dji-log-parser` binary used by [Loggflyt](https://github.com/olavbolav/Loggflyt). Below is the migration path.

### What changes in Loggflyt

Loggflyt's `app/core/parser.py` calls the Rust binary via subprocess:

```python
cmd = ["dji-log", "--api-key", self.api_key, "--output", output_path, input_path]
```

#### Option A: Symlink (zero code changes in Loggflyt)

The Docker image creates a `dji-log` symlink pointing to `dji-flightlog-parser`. If this parser is installed in the same container or `PATH`, Loggflyt works without any code changes:

```bash
# Already done in the Dockerfile, but if installing manually:
ln -s $(which dji-flightlog-parser) /usr/local/bin/dji-log
```

#### Option B: Use the Python API directly (recommended for production)

Replace the subprocess call with a direct Python import for better performance, error handling, and no process overhead:

```python
# app/core/parser.py — updated for dji-flightlog-parser
import json
import logging
from dji_flightlog_parser import DJILog
from dji_flightlog_parser.export.json_export import export_json, export_json_raw
from dji_flightlog_parser.export.geojson import export_geojson
from app.core.config import settings

logger = logging.getLogger(__name__)


class ParserService:
    def __init__(self):
        self.api_key = settings.DJI_PARSER_API_KEY

    def parse_log(self, input_path: str, output_path: str, timeout: int = 300):
        log = DJILog.from_file(input_path)
        keychains = log.fetch_keychains(self.api_key)
        frames = log.frames(keychains)
        json_str = export_json(log.version, log.details, frames, output_path)
        return json.loads(json_str)

    def parse_log_raw(self, input_path: str, output_path: str, timeout: int = 300):
        log = DJILog.from_file(input_path)
        keychains = log.fetch_keychains(self.api_key)
        records = log.records(keychains)
        json_str = export_json_raw(log.version, log.details, records, output_path)
        return json.loads(json_str)

    def generate_geojson(self, input_path: str, output_path: str):
        log = DJILog.from_file(input_path)
        keychains = log.fetch_keychains(self.api_key)
        frames = log.frames(keychains)
        export_geojson(log.details, frames, output_path)
        return True
```

### JSON output compatibility

The JSON output structure is compatible with the Rust parser, extended with additional fields:

```json
{
  "version": 14,
  "summary": {
    "startTime": "2026-04-01T16:38:33.928000Z",
    "startCoordinate": { "latitude": 59.7698, "longitude": 9.8774 },
    "totalTime": 1741.4,
    "totalDistance": 1.59,
    "maxHeight": 71.0,
    "maxHorizontalSpeed": 11.67,
    "maxVerticalSpeed": 6.0,
    "aircraftName": "Matrice 4TD",
    "aircraftSn": "1581F8HGX255M00A",
    "cameraSn": "53HFN470M7XDLE",
    "rcSn": "8L5CN2M00131D2",
    "batterySn": "87UPN3ACA000MR",
    "componentSerials": { "RightCamera": "1581F8HGX255M00A0EX2" },
    "firmwareVersions": [
      { "senderType": 1, "subSenderType": 0, "version": "40.0.7" }
    ],
    "batteryCycleCount": 2,
    "batteryDesignedCapacity": 7420
  },
  "frames": [
    {
      "osd": {
        "flyTime": 0.0,
        "latitude": 59.7698,
        "longitude": 9.8774,
        "altitude": 45.2,
        "height": 42.1,
        "xSpeed": 0.1,
        "ySpeed": -0.2,
        "zSpeed": 0.0,
        "pitch": 2.5,
        "roll": -1.0,
        "yaw": 180.0,
        "flycState": "GPSAtti",
        "gpsNum": 30,
        "gpsLevel": 5,
        "isOnGround": false,
        "isMotorOn": true,
        "voltageWarning": 0
      },
      "gimbal": { "pitch": -45.0, "roll": 0.0, "yaw": 180.0 },
      "rc": { "aileron": 1024, "elevator": 1024, "throttle": 1024, "rudder": 1024 },
      "battery": {
        "chargeLevel": 96,
        "voltage": 24.592,
        "current": 1.29,
        "temperature": 21.7,
        "cycleCount": 2,
        "designedCapacity": 7420
      },
      "camera": { "isPhoto": false, "isVideo": true },
      "appGps": {
        "latitude": 59.7698,
        "longitude": 9.8773,
        "horizontalAccuracy": 117.6
      },
      "vision": {
        "collisionAvoidanceEnabled": false,
        "isBraking": false,
        "isAscentLimited": false,
        "isLandingConfirmationNeeded": false
      },
      "flightController": {
        "remainingFlightTime": 1200,
        "batteryPercentNeededToLand": 10,
        "batteryPercentNeededToGoHome": 25
      },
      "nearbyAircraft": [
        {
          "icaoAddress": "4aca15",
          "latitude": 59.9732,
          "longitude": 10.1469,
          "altitude": 4776,
          "heading": 42.8
        }
      ]
    }
  ]
}
```

The `nearbyAircraft` array contains ADS-B data from the drone's AirSense receiver. Each entry represents a manned aircraft detected during the flight, with its ICAO transponder address, position, barometric altitude (feet), and track heading (degrees). The array is empty when no aircraft are nearby.

### Loggflyt Docker integration

Add `dji-flightlog-parser` to Loggflyt's Docker image. In Loggflyt's `Dockerfile`:

```dockerfile
# Install dji-flightlog-parser from the git repository
RUN pip install --no-cache-dir git+https://github.com/olavbolav/dji_flightlog_parser.git

# Create dji-log symlink for backward compatibility
RUN ln -s $(which dji-flightlog-parser) /usr/local/bin/dji-log
```

Or if using Option B (direct Python API), just add to Loggflyt's `requirements.txt`:

```
dji-flightlog-parser @ git+https://github.com/olavbolav/dji_flightlog_parser.git
```

## Testing

```bash
# Unit tests only (no API key needed)
pytest tests/test_xor.py tests/test_prefix.py tests/test_osd.py tests/test_feature_point.py -v

# Full test suite (requires example files and API key in .env)
pytest tests/ -v
```

## Requirements

- Python 3.10+
- DJI Developer API key (for v13+ log decryption)

## License

MIT
