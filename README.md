# dji-flightlog-parser

DJI flight log parser and decryptor for version 13 and 14 log files. Decrypts, parses, and exports DJI flight telemetry to JSON, GeoJSON, KML, and CSV.

## Features

- Full decryption of v13/v14 DJI flight logs via the DJI OpenAPI keychains endpoint
- CRC64-based XOR decoding and AES-256-CBC decryption with IV chaining
- Comprehensive record parsing: OSD, Home, Gimbal, RC, Battery, Camera, GPS, IMU, OFDM, Vision/Perception, Navigation, and more
- ADS-B / DJI AirSense support: nearby manned aircraft with ICAO address, position, altitude, heading, distance and warning level
- Battery data: aggregate and per-pack values on dual-battery aircraft, cycle count, designed capacity, state of health, manufacture date, battery serials
- Obstacle-avoidance setting and near-ground state
- Flight controller estimates: remaining flight time, battery reserves and time needed for landing/go-home, RC-lost action
- Wind estimate, positioning source, RC buttons and dials (with `--extended`)
- Controller/app GPS position and altitude
- Component serial numbers and firmware versions in flight summary
- Frame aggregation into normalized ~10 Hz telemetry frames
- JSON output compatible with the Rust `dji-log-parser` (drop-in replacement)
- GeoJSON, KML, and CSV export
- Keychain response caching for repeated parsing
- Automatic keychain department fallback for logs recorded through the DJI Mobile SDK
- CLI with the same interface as the Rust `dji-log-parser` tool

## Extracted Data Reference

Every frame (emitted at ~10 Hz) contains the following data groups. The summary is emitted once per flight by `parse_file()`; keys after `productType` appear only when the log carries the value. Some values from the records are range-checked: a value outside the range given in its row counts as unknown.

When `parse_file()` gets a v13 or v14 log without keys, the records stay encrypted. That is the case with no `api_key`, and also when the keychains hold no key: the key API returns no keychains, or only empty groups and items the parser cannot use (missing key or IV, unknown feature point name), which gives a list of empty keychains such as `[{}]`. Such a result is cached like any other, so later runs read it from the cache (`~/.cache/dji-flightlog-parser`) instead of asking the API again. The summary then has only the 15 keys from `startTime` to `productType`, taken from the log header; the Recover record does not fill in missing serials or the aircraft name, and every key after `productType` is left out. The frames of such a log are still emitted, but most of their values are noise. `DJILog.records()` logs a warning when it gets keychains without a key for a v13 or v14 log.

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
| `aircraftName` | string | Aircraft name from the log header: the model name (e.g. "Matrice 4TD") in most of our logs, but it can also be a generic default such as "dji aircraft" or a name the user gave the aircraft |
| `aircraftSn` | string | Aircraft serial number |
| `cameraSn` | string | Camera serial number |
| `rcSn` | string | Remote controller serial number |
| `batterySn` | string | Battery serial number, from the log header. On dual-battery aircraft (M30, M300, M350) this is the battery in slot 1 (the same as `batterySns[0]`). It cannot be matched to the pack that `batteryCycleCount`, `batteryDesignedCapacity`, `batteryStateOfHealth` and `batteryManufactureDate` describe |
| `appPlatform` | string | Controller app platform, as the enum name: `Android`, `IOS`, `DJIFly`, `Windows`, `Mac` or `Linux`; `Unknown` when not set or not recognised |
| `appVersion` | string | Controller app version |
| `productType` | string | DJI product type, as the enum name (e.g. `Matrice350RTK`); `NONE` for products the table does not know, such as Matrice 4TD, Matrice 400, Mini 5 Pro, Neo and Neo 2 |
| `componentSerials` | object | Map of component name to serial (e.g. `{ "RightCamera": "..." }`) |
| `firmwareVersions` | array | One entry per module and firmware version (in practice one per module): `[{ senderType, subSenderType, version, senderName, fullVersion }]`. `senderName` is the module (`Camera`, `FlightController`, `Gimbal`, `RemoteController`, `Battery`, ...). `subSenderType` is the module index: for `Battery` the battery slot; for `Camera`/`Gimbal` on M300/M350 the gimbal port of the payload (0, 1 = port 1, 2). On the Matrice 4TD the built-in camera is 0, and a second `Gimbal` with index 2 appears on airframes with an accessory on the top port (most likely the AL1 spotlight). On the Matrice 400 a single H30T is reported at 1 or 2; the port numbering there is not confirmed. `version` has the first three version numbers, `fullVersion` all four |
| `cameraType` | int | DJI payload type code of the main camera (e.g. 43 Zenmuse H20T, 61 H20N, 83 H30T, 53 Matrice 30T, 99 Matrice 4TD) |
| `cameraModel` | string | Model name for `cameraType`; `null` when the code is not in the table |
| `batteryCycleCount` | int | Battery charge cycle count, from the static battery record. Only one pack is logged per flight: on dual-battery aircraft (M30, M300, M350) pack 1, or pack 2 when the log only has that one; `batteries[].index` (1 or 2) says which. On these aircraft the value cannot be matched to `batterySn` or `batterySns`, for pack 1 as well as pack 2: the pack index is not tied to a slot. In our logs one battery pair, in the same slots and with the same `batterySn`, reports a lower cycle count in a later flight than in an earlier one, so the two flights logged different packs. Do not key cycle counts or state of health by battery serial on dual-battery aircraft |
| `batteryDesignedCapacity` | int | Factory designed capacity (mAh), same pack as `batteryCycleCount` |
| `batteryStateOfHealth` | int | State of health (%) reported by the battery, same pack as `batteryCycleCount`. Omitted unless it is 1–110: 0 means unknown (always on Mini 5 Pro), and one M400 log reads 101 |
| `batteryManufactureDate` | string | Pack manufacture date (`YYYY-MM-DD`), same pack as `batteryCycleCount` |
| `batteries` | array | One entry per logged pack: `[{ index, cycleCount, designedCapacity, stateOfHealth, manufactureDate }]`. `index` is 0 on single-battery aircraft and 1 or 2 on dual-battery aircraft. Unknown values are `null`; `stateOfHealth` is `null` unless it is 1–110 |
| `batterySns` | array | Battery serials from record 253, in slot order (slot 1, then slot 2 on dual-battery aircraft). A slot is not a pack index: the same battery can be in either slot in different flights. v14 enterprise aircraft only |
| `accessorySn` | string | Accessory serial from record 253. Seen only on M4TD (10 of 14 logs); which accessory it belongs to is not confirmed |
| `rcLostAction` | string | Action when the RC signal is lost: `Hover`, `Landing` or `GoHome` |
| `lowBatteryWarningThreshold` | int | Low-battery warning level (%): the first OSD value in 1–100 |
| `criticalBatteryWarningThreshold` | int | Critical-battery warning level (%): the first OSD value in 1–100 |
| `aircraftFlightCount` | int | Flight counter of the aircraft, including this flight: the last Home value in 1–1,000,000. Mini 5 Pro and Neo 2 only |
| `maxWindSpeed` | float | Highest wind speed estimated by the aircraft (m/s), over the OSD values in 0–40 m/s. v14 logs only |
| `batterySerial` | string | Never emitted: the parser has no source for it. Use `batterySn` or `batterySns` |

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
| `droneType` | string | Aircraft type name (e.g. `Matrice350RTK`, `Matrice4D`, `Neo2`); the code as a string for types not in the table |
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
| `pitch` / `roll` / `yaw` | float | Gimbal angles (degrees). `yaw` is in the gimbal's own yaw frame, not a bearing (see below) |
| `isPitchAtLimit` | bool | Pitch axis at mechanical limit |
| `isRollAtLimit` | bool | Roll axis at mechanical limit |
| `isYawAtLimit` | bool | Yaw axis at mechanical limit |
| `isStuck` | bool | Gimbal stuck |

`gimbal.yaw` differs from true north by an offset. The offset stays about the same for a power cycle on M300, M350, M30 and Neo 2, but can move by tens of degrees on M4TD, Mini 5 Pro, Mavic Mini and Neo. Do not use it as the camera bearing. Use `osd.yaw` + `gimbal.yawRelativeToAircraft` (`--extended`) on M300, M350, M30 and Mavic Mini, and `osd.yaw` alone on the other aircraft.

On Matrice 4TD airframes with a top accessory (most likely the AL1 spotlight), the gimbal records interleave two devices. `gimbal` follows the camera gimbal only: the device whose roll stays level, as a camera gimbal keeps the horizon. The accessory is in `secondaryGimbal` with `--extended`. Versions of the parser before November 2026 mixed the two, so on those airframes `gimbal` often showed the accessory: roll followed the aircraft instead of staying level, and the pitch-endpoint tip was repeated. Pitch was mostly unaffected, because the accessory tilts with the camera, except that it stops at +35° when the camera tilts higher.

### Camera

| Field | Type | Description |
|---|---|---|
| `isPhoto` | bool | `true` in a frame that received a camera record reporting a photo capture (single, burst, HDR or panorama). Camera records arrive about once a second, and unlike the other camera fields this flag is reset every frame, so a long capture shows up about once a second. It is not a photo count |
| `isVideo` | bool | Video recording active |
| `sdCardIsInserted` | bool | SD card present |
| `sdCardState` | string | SD card state (`Normal`, `NotInserted`, `Full`, `Slow`, `SuggestFormat`, ...) |

Versions of the parser before November 2026 read these four fields from the wrong bits. On v14 logs `isPhoto` was `true` in every frame that received a camera record (about one in ten), `isVideo` was fixed per aircraft model (`true` on M30/M300/M350/M400, `false` on M4TD and consumer drones), `sdCardIsInserted` was almost always `false`, and `sdCardState` was usually `Invalid` (`IllegalFileSystem` on most M300 logs). None of them reflected the real camera state.

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
| `chargeLevel` | int | State of charge (%) |
| `voltage` | float | Battery voltage (V) |
| `current` | float | Discharge current (A) |
| `currentCapacity` | int | Remaining capacity (mAh) |
| `fullCapacity` | int | Full charge capacity (mAh) |
| `cellNum` | int | Number of cells in series, taken from the log's battery records (13 on M400, 12 on M300/M350, 6 on M30 and M4TD, 2 on Mavic Mini, Mini 5 Pro, Neo and Neo 2). Falls back to a per-product table when the log has no cell count (4 for products the table does not know) |
| `cellVoltages` | array | Per-cell voltages (V) of one pack (pack 1 on dual-battery aircraft). Estimated as `voltage / cellNum` when no cell record arrived in the last 5 s. M30, M300 and M350 log no regular cell records, so their values are estimated |
| `isCellVoltageEstimated` | bool | True if cell voltages are computed from total voltage |
| `cellVoltageDeviation` | float | Max-min cell voltage difference (V) |
| `maxCellVoltageDeviation` | float | Highest cell deviation during flight (V) |
| `temperature` | float | Battery temperature (°C) |
| `minTemperature` / `maxTemperature` | float | Temperature range during flight (°C) |
| `cycleCount` | int | Charge cycle count, from the static battery record (same pack as the summary `batteryCycleCount`). On M30, M300 and M350 this is whichever single pack logged its static record (summary `batteries[].index` 1 or 2), and it cannot be matched to `batterySn` or `batterySns` |
| `designedCapacity` | int | Factory designed capacity (mAh), same pack as `cycleCount` |
| `batterySerial` | string | Always `null`: the parser has no source for it. The summary has `batterySn` and `batterySns` |

On dual-battery aircraft (M30, M300, M350) the values are the aggregate of both packs: `currentCapacity`, `fullCapacity` and `current` are the sums, `voltage` is the mean of the two packs, `temperature` is the hotter pack, and `chargeLevel` is the combined state of charge. The single packs are in `battery.packs` with `--extended`.

The aggregate record can start a little after the first frame: 2–18 frames (0.2–1.8 s) late in 10 of our 27 dual-battery logs. Until it arrives, `current`, `currentCapacity` and `fullCapacity` stay 0 (extended `remainingEnergy` stays `null`). In 7 of these 10 logs a pack-1 record comes before it and fills `chargeLevel`, `voltage` and `temperature` from then on (the pack's charge is within 1–2 % of the aggregate, but its voltage can be off by up to about 0.2 V); `minTemperature` and `maxTemperature` start again at the first aggregate record. In the other 3, `chargeLevel` and `voltage` come only from the SmartBattery record (type 8) where the aircraft writes one. `temperature` stays 0 for the first 5–9 frames in 4 of the 10 logs: those 3, and one where the first pack-1 record arrives only at frame 7 (type 8 fills `chargeLevel` and `voltage` there until then). Pack 2 never stands in for the aggregate.

The battery values ignore a SmartBatteryGroup dynamic record (type 22) that is truncated, i.e. ends before the state of charge (`is_truncated` in raw output; for example the last record of a v12 log that was cut off inside it), or that is physically implausible (more than 100 V, or a temperature below -50 °C or above 150 °C). Such a record is also left out of `battery.packs` and of the per-log choice of battery index and cell count. None of our 74 decrypted logs has a truncated dynamic record; one M350 log has two implausible ones.

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
| `altitude` | float | Controller/phone altitude (meters), in the same vertical reference as the aircraft's GNSS heights. `null` until the first record |
| `horizontalAccuracy` | float | Deprecated: the same value as `altitude` (-1.0 until the first record), kept for compatibility. It was never a horizontal accuracy. In Python, `FrameAppGPS.horizontal_accuracy` is a read/write alias of `altitude`: setting it to -1.0 or `None` sets `altitude` to `None`. It is not a constructor argument |

The App GPS record exists only in enterprise logs (M30, M300, M350, M400, M4TD).

### Vision — Obstacle Avoidance State

| Field | Type | Description |
|---|---|---|
| `collisionAvoidanceEnabled` | bool | Obstacle avoidance switched on by the pilot (VisionGroup record, type 17). Constant within a log. `false` before the first VisionGroup record and in logs without one (30 of our 74 logs), whatever the setting |
| `isBraking` | bool | Always `false`: the log has no supported source for it |
| `isAscentLimited` | bool | Always `false`: the log has no supported source for it |
| `isLandingConfirmationNeeded` | bool | Always `false`: the log has no supported source for it. A landing confirmation shows as `osd.flycState` `ConfirmLanding` |

### Flight Controller — Battery and Time Estimates

| Field | Type | Description |
|---|---|---|
| `remainingFlightTime` | int | Estimated remaining flight time (seconds) |
| `batteryPercentNeededToLand` | int | Battery % needed to land at current position |
| `batteryPercentNeededToGoHome` | int | Battery % needed to return to home point and land. `null` while the aircraft has no go-home estimate |

The source is the FlightControllerCommonOSD record (type 63, about 1 Hz) on M30, M400, M4TD, Mini 5 Pro, Neo and Neo 2. There `batteryPercentNeededToGoHome` is `null` while the record has no go-home estimate (time needed 65535, extended `timeNeededToGoHome` `null`), until the next record with one: the record then reads 0 %, which means unknown, not 0 %. This happens in 30 of our 74 logs, for whole flights in some Neo 2 logs. M300, M350 and Mavic Mini have no type 63; there the SmartBattery record (type 8) fills the same keys. Each key is then `null` until its first non-zero value: remaining flight time usually arrives 20–40 s into the log. `batteryPercentNeededToGoHome` stays `null` on Mavic Mini. On Mavic Mini, `batteryPercentNeededToLand` is always 5 in our logs, the same as `criticalBatteryWarningThreshold`: a fixed reserve rather than an estimate.

### Nearby Aircraft — ADS-B / DJI AirSense

Array of detected manned aircraft (empty when none are nearby). ADS-B records exist only on enterprise aircraft (M30, M300, M350, M400, M4TD).

| Field | Type | Description |
|---|---|---|
| `icaoAddress` | string | ICAO 24-bit transponder address (6 lowercase hex digits) |
| `latitude` / `longitude` | float | Aircraft position (degrees) |
| `altitude` | int | Altitude (meters, not feet). On M400 and M4TD a WGS84 ellipsoidal height (in Norway about 35–48 m more than the height above mean sea level), on M350 the height above mean sea level; `altitudeType` with `--extended` gives the reference. Not barometric |
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

Versions of the parser before November 2026 skipped two internal v14 record types (253 and 254) instead of decrypting them. These records share a key chain with the app messages and the Custom record that sets `custom.dateTime`. The first 16 bytes of the next record in that chain were then garbled. In the 70 v14 logs we have:
- About one in ten app messages started with unreadable characters, and some were empty.
- `custom.dateTime` was wrong in about 15% of frames, with dates hundreds or thousands of years off that jumped back and forth.

Both are now correct.

### Changes to default values

Versions of the parser before November 2026 read some default frame values from the wrong bytes or the wrong records. In the 74 logs we can decrypt (70 v14, 4 v12), these values change (the last item is about the 18 further v14 logs we have no keys for):
- `battery.chargeLevel` and `battery.voltage` on M300, M350 and Mavic Mini: the SmartBattery record (type 8) was read one byte off, so it gave the low-battery warning threshold (20–30%) as `chargeLevel` and a wrong `voltage` (about 5–24 V). On M300, M350 and the one Mavic Mini log that also has SmartBatteryGroup dynamic records, these values alternated with the real ones. On the other three Mavic Mini logs type 8 was the only battery source, so `chargeLevel` was the threshold and `voltage` was wrong (16–22 V for a 7.4–7.9 V pack) in every frame.
- `battery` on M30, M300 and M350: the values came from pack 1 only. They are now the aggregate of both packs (see Battery), so `currentCapacity`, `fullCapacity` and `current` are about twice the old values. In the first frames of some logs, before the first aggregate record, these three are now 0 (see Battery).
- `battery.cycleCount` and `battery.designedCapacity`, and the summary keys `batteryCycleCount` and `batteryDesignedCapacity`, were missing in the 11 of 27 dual-battery logs that only log pack 2. They are now set from pack 2. Like the pack-1 values in the other dual-battery logs, they cannot be matched to `batterySn` or `batterySns` (see Summary).
- `flightController.batteryPercentNeededToGoHome` on M30, M400, M4TD, Mini 5 Pro, Neo and Neo 2 was 0 while the type-63 record had no go-home estimate. It is now `null` there (see Flight Controller): 6,893 of 738,677 frames in 30 of our 74 logs, most of them on Neo 2 and Neo. The CSV cell is empty in those frames.
- `battery.cellNum` and `battery.cellVoltages`: the cell count came from a product table that does not know the newer aircraft and gave 4. It now comes from the log: 13 on M400, 6 on M4TD, 2 on Mini 5 Pro, Neo and Neo 2. Cell records with a 2-byte header and the truncated M4TD records were also misread. Together this gave `maxCellVoltageDeviation` values up to 4.1 V on M4TD, Mini 5 Pro, Neo and Neo 2, and 8.7 V and 63 V in one M300 and one M350 log, where a single misread cell record stayed in place for the whole flight.
- `flightController` on M300, M350 and Mavic Mini was always `null`. It is now filled from the type-8 record (see Flight Controller).
- `vision.collisionAvoidanceEnabled` was always `false`, because the VisionGroup record (type 17) was split at the wrong place. It now shows the obstacle-avoidance setting.
- `osd.droneType` was a number for seven aircraft and is now a name: 53 `MavicMini`, 67 `Matrice30`, 100 `Matrice4D`, 103 `Matrice400`, 104 `Neo`, 112 `Mini5Pro`, 124 `Neo2`.
- The summary of a v13 or v14 log parsed without keys (or with keychains that hold no key) used to contain values read from the still-encrypted records. For the 18 v14 logs we have no keys for, every summary had `cameraType`, `cameraModel` and `firmwareVersions` made from noise, 15 had a `batteryCycleCount`, 1 had `componentSerials`, and 4 had `cameraSn` filled in from a garbled Recover record. The summary now has only the 15 header keys (see Summary).

Values derived from these (`minTemperature`, `maxTemperature`, the cell deviations, `isCellVoltageEstimated`) change with them; no other default key changes value. `appGps.altitude` is a new key. `appGps.horizontalAccuracy` and `nearbyAircraft[].altitude` keep their values but were documented wrongly: the first is the controller altitude, the second is in meters, not feet. The CSV export has the same columns as before.

### Extended sections (`--extended` only)

With `--extended` (or `records_to_frames(..., extended=True)`), each frame also gets five sections with data that the default output leaves out, and the default sections get extra keys (listed after the five sections). Values carry forward between records and are `null` until the first record of that kind arrives. Aircraft that never write a record type (for example enterprise aircraft and type 54) still get that section or key, with the value `null`. Without the flag, frames have only the default keys.

**`rtk`** — RTK/GNSS module status (record type 45, 1 Hz)

| Field | Type | Description |
|---|---|---|
| `positionSolution` | string | `Single`, `Float`, `Fixed`, `Code52` (undocumented, M400 only; not shown to be precise) or `UNKNOWN` |
| `positionSolutionCode` | int | Raw solution code (16 / 34 / 50 / 52) |
| `latitude` / `longitude` | float | RTK antenna position (degrees) |
| `height` | float | RTK antenna height (m); likely ellipsoidal, not relative to take-off |
| `stdLatitude` / `stdLongitude` / `stdAltitude` | float | 1-sigma error (m) |
| `satellites` | int | Satellites tracked by receiver 1 (all constellations) |
| `gpsSatellites` / `beidouSatellites` / `glonassSatellites` / `galileoSatellites` | int | Per constellation |
| `hasBase` | bool | Corrections from a base / network station |
| `correctionAge` | float | Age of the corrections (s) |
| `dualAntennaHeading` | float | Dual-antenna baseline heading (degrees, 90° off the nose); `null` on single-antenna aircraft |

**`airLink`** — radio link (record type 57, ~5 Hz)

| Field | Type | Description |
|---|---|---|
| `sdrLinkUp` / `lteLinkUp` | bool | OcuSync (SDR) and 4G/LTE link connected |
| `sdrQuality` / `lteQuality` | int | Link quality 0–5 (0 = no usable signal) |
| `linkQuality` | int | Fused 0–5 level shown in the pilot app |
| `workMode` | string | `SdrOnly` or `SdrLte` (LTE-enhanced transmission enabled) |
| `lteLevelA` / `lteLevelB` | int | The two LTE side levels (probably aircraft and RC side) |

**`navigation`** — flight-controller navigation state (record type 48, 10 Hz; M30/M300/M350/M4TD/M400)

| Field | Type | Description |
|---|---|---|
| `aircraftClock` | float | Aircraft clock (s, Unix-like). Not uniformly UTC: UTC + 1 h on M30/M300/M350, UTC or UTC + 18 s on M4TD/M400 |
| `satellitesUsed` | int | Satellites in the position solution in use |
| `distanceToHome` | float | Horizontal distance to the home point (m) |
| `isRtkFixed` | bool | Flight controller navigates on an RTK fixed solution |
| `relativeHeight` | float | Height above take-off at full precision (m) |
| `gnssHeight` | float | Standalone GNSS height (m) |
| `geoidUndulation` | float | Geoid separation at home (m); `null` when unavailable |

**`appHud`** — DJI Fly on-screen notifications (record type 54; consumer aircraft only)

| Field | Type | Description |
|---|---|---|
| `statusBar` / `statusBarLevel` | string / int | Top status label (e.g. "In flight") and severity 1–3 |
| `tip` / `tipCode` | string | Current pop-up tip and its app code |
| `warnings` | array | Active warnings `[{ text, code, level }]`; `code` is the `(Code: X)` suffix. `[]` once the app reports an empty list |

**`secondaryGimbal`** — a second gimbal device in the gimbal records (record type 3). Seen only on Matrice 4TD airframes with a top accessory, most likely the AL1 spotlight. It tilts in pitch only, and its pitch and yaw follow the camera gimbal, with a stop at +35° (seen in the one log where the camera tilted higher). Its roll follows the aircraft. On all other aircraft, and on a Matrice 4TD without an accessory, the section is present but every field is `null`

| Field | Type | Description |
|---|---|---|
| `pitch` / `roll` / `yaw` | float | Angles (degrees) |
| `isPitchAtLimit` | bool | Pitch axis at its limit (same flag as in `gimbal`). Never set in the logs we have, not even while the accessory sits at its +35° stop |

**Extra keys in the default sections.** They are added after the default keys of each section.

`osd` (OSD record, type 1)

| Field | Type | Description |
|---|---|---|
| `windSpeed` | float | Wind speed estimated by the aircraft (m/s); 0 = calm or no estimate. `null` on v12 logs, and when the record reads 255 (no value; seen only in records that were not decrypted) |
| `windDirection` | string | Direction the wind blows from: `N`, `NE`, `E`, `SE`, `S`, `SW`, `W` or `NW`; `null` when calm, when `windSpeed` is `null`, and on v12 logs |
| `positionSource` | string | Positioning source of the flight controller: `None`, `Vision`, `GNSS` or `RTKFixed` (`Unknown(n)` for other codes). `null` on v12 logs |
| `positionSourceCode` | int | Raw code (0–3 in our logs) |
| `yawRate` | float | Yaw rate (deg/s, positive = clockwise seen from above) |
| `homeOffsetNorth` / `homeOffsetEast` | float | Position relative to the home point (m, north and east). M400, M4TD, Mini 5 Pro, Neo and Neo 2 only; `null` without a GNSS fix |

`battery`

| Field | Type | Description |
|---|---|---|
| `stateOfHealth` | int | State of health (%) from the static battery record; `null` when the battery reports 0 (unknown) |
| `remainingEnergy` | float | Remaining energy (Wh), the battery's own estimate. M30, M400, Mini 5 Pro, Neo and Neo 2 only |
| `lowWarningThreshold` / `criticalWarningThreshold` | int | Low and critical battery warning levels (%) |
| `packs` | array | Dual-battery aircraft only (M30, M300, M350): `[{ index, chargeLevel, voltage, current, currentCapacity, fullCapacity, temperature }]` for packs 1 and 2, from the latest record of each pack. `null` on single-battery aircraft |

`gimbal` (camera gimbal only)

| Field | Type | Description |
|---|---|---|
| `yawRelativeToAircraft` | float | Gimbal yaw relative to the aircraft heading (degrees). Meaningful on M300, M350, M30 and Mavic Mini. It does not behave as a joint angle on M4TD and Mini 5 Pro, and is always 0 on Neo and Neo 2 |
| `jointPitch` | float | Gimbal pitch relative to the airframe (degrees) |
| `isResetting` | bool | A gimbal reset (recenter or point down) was in progress in a record of this frame |

`camera`

| Field | Type | Description |
|---|---|---|
| `workMode` | int | 0 photo, 1 video, 2 playback, 7 new playback |
| `sdCardTotalMb` / `sdCardFreeMb` | int | Storage size and free space (MB) |
| `remainingPhotos` | int | Photos that still fit |
| `remainingVideoSeconds` | int | Video time that still fits (s) |

The four storage keys are `null` when the camera reports a total of 0 (Mavic Mini, one M350 log).

`rc` (RC display record, type 62; `null` in logs without it, such as Mavic Mini)

| Field | Type | Description |
|---|---|---|
| `isShutterHalfPressed` / `isShutterPressed` | bool | Shutter button half / fully pressed |
| `isRecordPressed` | bool | Record button pressed |
| `isCustomButton1Pressed` / `isCustomButton2Pressed` | bool | C1 / C2 button pressed (the pilot sets their function) |
| `leftDial` / `rightDial` | int | Dial positions on the stick scale (364–1684, centre 1024). The left dial tilts the gimbal. The right dial pans it on M300/M350, has no gimbal effect on M4TD and stays at about 1024 on Neo and Neo 2 |

The buttons are momentary: `true` when a record in the frame had the button down.

`vision`

| Field | Type | Description |
|---|---|---|
| `isNearGround` | bool | Ground within the range of the downward sensors. `null` before the first VisionGroup record and in logs without one |

`flightController` (same sources as the default keys)

| Field | Type | Description |
|---|---|---|
| `timeNeededToGoHome` | int | Estimated time to fly home (s); `null` while the aircraft reports no estimate |
| `timeNeededToLand` | int | Estimated time to land from the current height (s) |
| `rcLostAction` | string | Action when the RC signal is lost: `Hover`, `Landing` or `GoHome` |

`nearbyAircraft[]`

| Field | Type | Description |
|---|---|---|
| `distance` | int | Horizontal distance from the aircraft (m) |
| `relativeAltitude` | int | Traffic altitude minus aircraft altitude (m; positive = traffic above) |
| `verticalTrend` | string | `Level`, `Rising` or `Falling` |
| `warningLevel` | int | AirSense warning level: 1 tracked, 2 caution, 3 and up take action (only 1 and 2 seen) |
| `altitudeType` | string | Reference of `altitude`: `Ellipsoid` (WGS84; M400, M4TD) or `MSL` (M350) |

### Raw output (`--raw`)

`--raw` includes the seven newly decoded record types with all their fields: `RTKDifference` (45), `AgricultureGroundStationPush` (48), `AirLinkDataField` (57) and `GOBusiness` (54), plus three that appear only in raw output:

- `GSMissionStatus` (type 32): legacy Waypoint 1.0 mission status. It is always all zero in the logs we have, including DJI Pilot 2 waypoint flights.
- `Security` (type 55): an opaque 256-byte block that cannot be decrypted. The log has no key for it, and the block is not AES output. Only its check-byte and range diagnostics (`check_ok`, `in_range`) are exposed.
- `KeyValueSnapshot` (type 253, v14 logs only): `module`, `key`, `timestamp` (app clock, UTC), `serials` and `total_flight_time`. Module 7 key 1 lists component serials in `serials`, keyed by protobuf field number (a string in JSON): 1 matches the camera serial, 6 is an accessory (M4TD only), 7 and 8 are battery slots 1 and 2, and the role of 2 is unknown. Module 5 key 1 has `total_flight_time` (s), a flight-time counter whose owner (aircraft, RC or app) is not known. A log has one or two records at the start, and up to five when the app reconnects during the flight; consumer aircraft write one with empty `serials`. Record 254 is still decrypted but not emitted.

Renamed or removed keys in existing records: `OSD.battery` is now `sequence_counter`, `AppGPS.horizontal_accuracy` is now `altitude`, `SmartBatteryGroup` static `temperature` is now `manufacture_date`, and `VisionGroup` loses `is_braking`, `is_ascent_limited`, `is_landing_confirmation_needed` and `is_avoid_active_obstacle`. Details per record:

- `OSD` (type 1): byte 40 (`sequence_counter`, was `battery`) is a rolling counter that steps by about 5 per record, not battery data. `drone_type` is a name for seven more aircraft (see `droneType` above). New fields, set only when the record is long enough (see the extended `osd` keys): `low_battery_warning` and `critical_battery_warning` (%) with the flags `low_battery_warning_go_home` and `critical_battery_warning_landing`, `yaw_rate`, `position_source_code` / `position_source`, `wind_speed`, `wind_direction_code` / `wind_direction`, and `home_offset_north` / `home_offset_east`. The three wind fields are `null` when the wind byte reads 255, which happens only in records that were not decrypted.
- `SmartBattery` (type 8): `go_home_countdown` is one byte, not two, so `voltage`, `percent`, `low_warning`, `low_warning_go_home`, `serious_low_warning` and `serious_low_warning_landing` change value; they used to be read one byte off. `useful_time` is the remaining flight time (s), `go_home_time` / `land_time` are times needed (s), `go_home_battery` / `land_battery` the battery % needed, and `status` is the warning level (0 normal, 1 low, 2 critical).
- `SmartBatteryGroup` (type 22): `static.manufacture_date` (`YYYY-MM-DD`, `null` when invalid) replaces `static.temperature`, which was these bytes misread. `static.life` is the state of health (%, 0 = unknown). `dynamic.remaining_energy` (Wh) is new; it is `null` on M300, M350, M4TD and Mavic Mini. On dual-battery aircraft `dynamic` index 0 is the aggregate of both packs, and 1 and 2 are the single packs. `dynamic.is_truncated` is new: `true` when the record is shorter than 22 bytes, so it ends before the state of charge (record byte 21) and the missing fields read 0; a record with only one byte after the kind byte even reads as index 0. The frames ignore such a record (see Battery). It is `false` in every dynamic record of our 74 decrypted logs. `single_voltage` now decodes the variant with a 2-byte header (30-byte M400, 16-byte M4TD and 28-byte M300/M350 records), which used to give a cell count of 0 or a garbage cell, and has a new `is_truncated` for the 6-byte M4TD records that carry only cell 1.
- `VisionGroup` (type 17): the record is now split into its blocks correctly, so `collision_avoidance_enabled` has real values. The four removed flags have no bit supported by the data or the upstream parser. New: `vert_low_limit_active` (ground within downward sensing range) and `avoidance_flags`, the raw status bitfield, which also shows the bits without a confirmed meaning.
- `MCParams` (type 19): the `fail_safe` names were swapped. Now 0 is `Hover`, 1 `Landing` and 2 `GoHome`, so logs that showed `Hover` now show `GoHome` and the other way round (63 of our 74 logs are `GoHome`). New, after the old keys: `mvo_func_enabled`, `avoid_obstacle_enabled` and `user_avoid_enabled` (byte 1, bits 0x01, 0x02 and 0x04, named as in the upstream parser). The old keys `e_landing`, `go_home_altitude` and `dynamic_home_point` read the same three bits and always equal the new ones. They are misnomers, kept for compatibility, and will be removed in a later change of the raw format. In particular, `dynamic_home_point` is not the dynamic home point setting: that is `Home.is_dynamic_home_point_enabled` (`home.isDynamicHomePointEnabled`), which is off in all 74 of our logs, while bit 0x04 is set in 61. `user_avoid_enabled` is the pilot's obstacle-avoidance switch; it matches `vision.collisionAvoidanceEnabled` in all 44 logs that have both records.
- `AppGPS` (type 14): `altitude` (m, was `horizontal_accuracy`).
- `FCCommonOSD` (type 63): `need_go_home_time` is `null` instead of 65535 when the aircraft has no estimate. `go_home_capacity` then reads 0; the frames show `batteryPercentNeededToGoHome` as `null` there.
- `ADSBFlightData` (type 26): `altitude` is meters (see Nearby Aircraft above). New per aircraft: `warning_level`, `altitude_type` (0 WGS84 ellipsoid, 1 MSL), `relative_altitude`, `vertical_trend` (0 level, 1 rising, 2 falling) and `distance`.
- `RCDisplayField` (type 62): new `is_shutter_half_pressed`, `is_shutter_pressed`, `is_record_pressed`, `is_custom_button_1_pressed`, `is_custom_button_2_pressed` and `right_dial`. `gimbal` is the left dial.
- `Home` (type 2): new `has_go_home` and `aircraft_flight_count` (Mini 5 Pro and Neo 2 only). `is_beginner_mode` and `is_ioc_open` now read the right bits. None of these three bits is set in any of our logs.

Other notes on existing records in raw output:

- `Camera` (type 25) has new fields: `camera_type` and `camera_model` (the main payload), `photo_state`, `record_state`, `record_time` (s), SD card size and free space (MB), remaining photos and remaining video time (s), plus `is_connected` / `is_usb_connected` / `is_time_synced`. `record_time` is unreliable on several enterprise aircraft: it stops at 30 s (15 s in some Matrice 4TD logs) and stays there until the recording ends. This happens in every Matrice 4TD and Matrice 400 log with a recording and in some Matrice 350 logs, so use `record_state` to tell whether a recording runs.

  The existing `Camera` fields also change value in most v14 records, because they used to be read from the wrong bits: `is_shooting_single_photo` (now photo state = single, was the connected bit), `is_recording` (now record state, was the USB bit), `is_storing` (now byte 2 bit 0x08, was byte 0 bit 0x08), `has_sd_card` (now byte 1 bit 0x02, was 0x10) and `sd_card_state` (now byte 1 bits 0x3C, was 0x0F). `work_mode` is unchanged.
- `Gimbal` (type 3): new `joint_pitch` (pitch relative to the airframe) and `is_resetting`. `yaw_angle` is the yaw relative to the aircraft heading (see `yawRelativeToAircraft`). `is_stuck` now reads bit 0x40 instead of 0x20; neither is set in our logs. `version` (low nibble of byte 11) tells the two devices apart on Matrice 4TD airframes with a top accessory: 2 is the camera gimbal and 1 the accessory in every such log we have.
- `Custom` (type 5), `AppTip`, `AppWarn`, `AppSeriousWarn` and `GOBusiness` change value wherever they used to follow a skipped record 253 or 254 (see App Messages above). About 12,000 `Custom` records that used to be dropped as unreadable now appear in raw output.
- `Firmware` (type 15): `entries`, the full module list with `sender_name`, `sub_sender_type` (module index, see `firmwareVersions` above) and `full_version`. The old top-level fields still hold the first entry.

Raw output for a v14 enterprise log is therefore about 40–55% larger than before; type 48 alone runs at 10 Hz. `KeyValueSnapshot` adds only one to five records per log. Nested record fields (for example `ADSBFlightData.aircraft`, `SmartBatteryGroup` and `VisionGroup.detections`) are emitted as JSON objects instead of Python repr strings. Payloads that cannot be recognised, such as records left encrypted when a key is missing, stay out of the raw output.

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

# Add RTK, radio link, navigation, DJI Fly notification and second-gimbal sections to frames,
# and extra keys (wind, battery packs, RC buttons, ...) to the default sections
dji-flightlog-parser flight.txt --api-key YOUR_DJI_API_KEY --extended

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

# Frames from records you already have; extended=True adds the extended keys.
# Pass the log version: without it the cell count ignores the cell-count field
# of the dynamic battery records and comes only from the cell records or the
# per-product table (4 for products the table does not know)
from dji_flightlog_parser.frame.builder import records_to_frames
frames = records_to_frames(records, log.details, extended=True, version=log.version)

# Summary and frames as one dict (the summary is only built here)
from dji_flightlog_parser.parser import parse_file
result = parse_file("flight.txt", api_key="YOUR_DJI_API_KEY")

# Flight metadata
print(log.details.aircraft_name)
print(log.details.product_type)
```

Logs recorded by Mobile SDK apps carry `department=SDK` in their header, which the DJI keychains API rejects with `invalid ciphertext`. When no department is given, `fetch_keychains` then retries as other departments (DJIGO first) and accepts the first keys whose decrypted OSD records contain valid positions. The accepted keys are cached like any other result. Pass `department_fallback=False` to disable this, or `department=...` to request a specific department (cached separately).

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
### JSON output compatibility

The JSON output structure is compatible with the Rust parser, extended with additional fields:

```json
{
  "version": 14,
  "summary": {
    "startTime": "2030-01-01T00:00:00Z",
    "startCoordinate": { "latitude": 60.0, "longitude": 10.0 },
    "totalTime": 1741.4,
    "totalDistance": 1.59,
    "maxHeight": 71.0,
    "maxHorizontalSpeed": 11.67,
    "maxVerticalSpeed": 6.0,
    "aircraftName": "Matrice 4TD",
    "aircraftSn": "EXAMPLE-AIRCRAFT-SN",
    "cameraSn": "EXAMPLE-CAMERA-SN",
    "rcSn": "EXAMPLE-RC-SN",
    "batterySn": "EXAMPLE-BATTERY-SN",
    "appPlatform": "Android",
    "appVersion": "99.0.0",
    "productType": "NONE",
    "componentSerials": { "RightCamera": "EXAMPLE-COMPONENT-SN" },
    "firmwareVersions": [
      { "senderType": 1, "subSenderType": 0, "version": "99.0.1", "senderName": "Camera", "fullVersion": "99.0.1.2" },
      { "senderType": 3, "subSenderType": 0, "version": "99.0.2", "senderName": "FlightController", "fullVersion": "99.0.2.3" },
      { "senderType": 4, "subSenderType": 0, "version": "99.0.3", "senderName": "Gimbal", "fullVersion": "99.0.3.4" },
      { "senderType": 4, "subSenderType": 2, "version": "99.0.3", "senderName": "Gimbal", "fullVersion": "99.0.3.4" },
      { "senderType": 6, "subSenderType": 0, "version": "99.0.4", "senderName": "RemoteController", "fullVersion": "99.0.4.5" },
      { "senderType": 11, "subSenderType": 0, "version": "99.0.5", "senderName": "Battery", "fullVersion": "99.0.5.6" }
    ],
    "cameraType": 99,
    "cameraModel": "Matrice 4TD Camera",
    "batteryCycleCount": 2,
    "batteryDesignedCapacity": 7420,
    "batteryStateOfHealth": 99,
    "batteryManufactureDate": "2029-06-01",
    "batteries": [
      { "index": 0, "cycleCount": 2, "designedCapacity": 7420, "stateOfHealth": 99, "manufactureDate": "2029-06-01" }
    ],
    "batterySns": ["EXAMPLE-BATTERY-SN"],
    "accessorySn": "EXAMPLE-ACCESSORY-SN",
    "rcLostAction": "GoHome",
    "lowBatteryWarningThreshold": 30,
    "criticalBatteryWarningThreshold": 20,
    "maxWindSpeed": 6.2
  },
  "frames": [
    {
      "osd": {
        "flyTime": 0.0,
        "latitude": 60.0,
        "longitude": 10.0,
        "height": 42.1,
        "altitude": 45.2,
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
        "voltage": 25.0,
        "current": 2.0,
        "temperature": 20.0,
        "cycleCount": 2,
        "designedCapacity": 7420
      },
      "camera": { "isPhoto": false, "isVideo": true },
      "appGps": {
        "latitude": 60.0,
        "longitude": 10.0,
        "horizontalAccuracy": 100.0,
        "altitude": 100.0
      },
      "vision": {
        "collisionAvoidanceEnabled": true,
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
          "icaoAddress": "000000",
          "latitude": 60.1,
          "longitude": 10.2,
          "altitude": 1500,
          "heading": 90.0
        }
      ]
    }
  ]
}
```

The `nearbyAircraft` array contains ADS-B data from the drone's AirSense receiver. Each entry represents a manned aircraft detected during the flight, with its ICAO transponder address, position, altitude (meters; WGS84 ellipsoidal height on M400/M4TD, above mean sea level on M350), and track heading (degrees). The array is empty when no aircraft are nearby.

## Testing

```bash
# Unit tests only (no API key needed)
pytest tests/ --ignore=tests/test_integration.py -v

# Full test suite (needs example files, and an API key in .env or cached keychains)
pytest tests/ -v
```

The integration tests (`tests/test_integration.py`) read example logs from `example_files/` (git-ignored). v13 and v14 logs also need keychains: `app_key` in `.env`, or keychains cached by an earlier run in `~/.cache/dji-flightlog-parser`, so the tests can run offline; v12 logs need neither. A test skips when what it needs is missing. Reference values from real flights are not committed: put them in the git-ignored `example_files/expected.json`, for example `{"trondelag": {"firstFrameLatitude": ..., "firstFrameLongitude": ...}}` with the first-frame position from the Rust parser. The test that uses them skips without the file.

## Requirements

- Python 3.10+
- DJI Developer API key (for v13+ log decryption)

## License

MIT
