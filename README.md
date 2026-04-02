# dji-flightlog-parser

Enterprise-grade DJI flight log parser and decryptor for version 13 and 14 log files. Decrypts, parses, and exports DJI flight telemetry to JSON, GeoJSON, KML, and CSV.

## Features

- Full decryption of v13/v14 DJI flight logs via the DJI OpenAPI keychains endpoint
- CRC64-based XOR decoding and AES-256-CBC decryption with IV chaining
- Comprehensive record parsing: OSD, Home, Gimbal, RC, Battery, Camera, GPS, IMU, OFDM, Vision/Perception, Navigation, and more
- Frame aggregation into normalized ~10 Hz telemetry frames
- JSON output compatible with the Rust `dji-log-parser` (drop-in replacement)
- GeoJSON, KML, and CSV export
- Keychain response caching for repeated parsing
- CLI with the same interface as the Rust `dji-log` tool

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

This parser is a drop-in replacement for the Rust `dji-log` binary used by [Loggflyt](https://github.com/olavbolav/Loggflyt). Below is the migration path.

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

The JSON output structure matches the Rust parser:

```json
{
  "version": 14,
  "details": {
    "subStreet": "",
    "street": "",
    "city": "",
    "area": "",
    "isFavorite": false,
    "isNew": false,
    "needsUpload": false,
    "recordLineCount": 0,
    "aircraftName": "Matrice 4TD",
    "aircraftSN": "...",
    "cameraSN": "...",
    "rcSN": "...",
    "batteryUID": "...",
    "productType": "NONE",
    "startTime": "2025-06-10T08:15:00Z",
    "totalTime": 754.0,
    "totalDistance": 12345.6,
    "maxHeight": 120.0,
    "maxHorizontalSpeed": 15.2,
    "maxVerticalSpeed": 5.1,
    "photoNum": 0,
    "videoTime": 0
  },
  "frames": [
    {
      "osd": {
        "latitude": 63.318,
        "longitude": 10.300,
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
        "droneType": "UNKNOWN"
      },
      "gimbal": { "pitch": -45.0, "roll": 0.0, "yaw": 180.0 },
      "rc": { "aileron": 1024, "elevator": 1024, "throttle": 1024, "rudder": 1024 },
      "battery": { "chargeLevel": 85, "voltage": 44200, "current": 5600, "temperature": 28.0 },
      "camera": { "isPhoto": false, "isVideo": true }
    }
  ]
}
```

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
