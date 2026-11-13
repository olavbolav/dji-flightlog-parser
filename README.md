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
- RTK/GNSS status, radio link quality (OcuSync and LTE), flight-controller navigation state, DJI Fly on-screen notifications and the Matrice 4TD accessory gimbal (with `--extended`)
- Raw output of seven further record types, among them RTK status, radio link, navigation state and component serials (with `--raw`)
- Controller/app GPS position and altitude
- Component serial numbers and firmware versions in flight summary
- Frame aggregation into normalized ~10 Hz telemetry frames
- JSON output compatible with the Rust `dji-log-parser` (drop-in replacement)
- GeoJSON, KML, and CSV export
- Keychain response caching for repeated parsing
- Automatic keychain department fallback for logs recorded through the DJI Mobile SDK
- CLI with the same interface as the Rust `dji-log-parser` tool

## New in 0.3.0

Version 0.3.0 (November 2026) fixes several record decoders and adds the fields below; the linked tables describe each one. Default frames keep their key set apart from one new key, and all other new per-frame data needs `--extended`. Some default values change because of the fixes: see [Changes to default values](#changes-to-default-values).

**Default frames**

- [`appGps.altitude`](#app-gps--controllerphone-position): controller/phone altitude. `appGps.horizontalAccuracy` stays as a deprecated alias with the same value.

**Extended frames (`--extended`)**

New sections:

- [`rtk`](#section-rtk) (RTK/GNSS status; M30, M300, M350, M400, M4TD): `positionSolution`, `positionSolutionCode`, `latitude`, `longitude`, `height`, `stdLatitude`, `stdLongitude`, `stdAltitude`, `satellites`, `gpsSatellites`, `beidouSatellites`, `glonassSatellites`, `galileoSatellites`, `hasBase`, `correctionAge`, `dualAntennaHeading`
- [`airLink`](#section-airlink) (radio link; all v14 aircraft): `sdrLinkUp`, `lteLinkUp`, `sdrQuality`, `lteQuality`, `linkQuality`, `workMode`, `lteLevelA`, `lteLevelB`
- [`navigation`](#section-navigation) (flight-controller navigation state; M30, M300, M350, M400, M4TD): `aircraftClock`, `satellitesUsed`, `distanceToHome`, `isRtkFixed`, `relativeHeight`, `gnssHeight`, `geoidUndulation`
- [`appHud`](#section-apphud) (DJI Fly notifications; Mavic Mini, Mini 5 Pro, Neo, Neo 2): `statusBar`, `statusBarLevel`, `tip`, `tipCode`, `warnings` (`[{ text, code, level }]`)
- [`secondaryGimbal`](#section-secondarygimbal) (Matrice 4TD top accessory): `pitch`, `roll`, `yaw`, `isPitchAtLimit`

Extra keys in the default sections:

- [`osd`](#extra-keys-in-osd): `windSpeed`, `windDirection`, `positionSource`, `positionSourceCode`, `yawRate`, `homeOffsetNorth`, `homeOffsetEast`
- [`battery`](#extra-keys-in-battery): `stateOfHealth`, `remainingEnergy`, `lowWarningThreshold`, `criticalWarningThreshold`, `packs` (`[{ index, chargeLevel, voltage, current, currentCapacity, fullCapacity, temperature }]`)
- [`gimbal`](#extra-keys-in-gimbal): `yawRelativeToAircraft`, `jointPitch`, `isResetting`
- [`camera`](#extra-keys-in-camera): `workMode`, `sdCardTotalMb`, `sdCardFreeMb`, `remainingPhotos`, `remainingVideoSeconds`
- [`rc`](#extra-keys-in-rc): `isShutterHalfPressed`, `isShutterPressed`, `isRecordPressed`, `isCustomButton1Pressed`, `isCustomButton2Pressed`, `leftDial`, `rightDial`
- [`vision`](#extra-keys-in-vision): `isNearGround`
- [`flightController`](#extra-keys-in-flightcontroller): `timeNeededToGoHome`, `timeNeededToLand`, `rcLostAction`
- [`nearbyAircraft[]`](#extra-keys-in-nearbyaircraft): `distance`, `relativeAltitude`, `verticalTrend`, `warningLevel`, `altitudeType`

**Summary** (`parse_file()`, see [Summary](#summary-per-flight))

- New keys, each present only when the log carries the value (exception: `cameraModel` is present whenever `cameraType` is, and is `null` for a code not in the table; unknown values inside `batteries` entries are `null`): `cameraType`, `cameraModel`, `batteryStateOfHealth`, `batteryManufactureDate`, `batteries` (`[{ index, cycleCount, designedCapacity, stateOfHealth, manufactureDate }]`), `batterySns`, `accessorySn`, `rcLostAction`, `lowBatteryWarningThreshold`, `criticalBatteryWarningThreshold`, `aircraftFlightCount`, `maxWindSpeed`.
- `firmwareVersions` has one entry per module (it had one per firmware record) and each entry gains `senderName` and `fullVersion`.
- `batteryCycleCount` and `batteryDesignedCapacity` now also come from pack 2 when a dual-battery log only has that pack.
- A v13 or v14 log parsed without a usable key gets only the 15 header keys.

**Raw output (`--raw`)**

- Seven newly decoded record types, each with its own table: [`RTKDifference`](#rtkdifference-type-45) (45), [`AgricultureGroundStationPush`](#agriculturegroundstationpush-type-48) (48), [`AirLinkDataField`](#airlinkdatafield-type-57) (57), [`GOBusiness`](#gobusiness-type-54) (54), [`GSMissionStatus`](#gsmissionstatus-type-32) (32), [`Security`](#security-type-55) (55) and [`KeyValueSnapshot`](#keyvaluesnapshot-type-253) (253). In 0.2.1 the first six were left out of the raw output as unknown records, and 253 was not emitted (0.2.1 builds from late October 2026 decrypted it, earlier ones skipped it).
- New fields in existing records:
  - [`OSD`](#osd-type-1): `sequence_counter` (renamed from `battery`), `low_battery_warning`, `low_battery_warning_go_home`, `critical_battery_warning`, `critical_battery_warning_landing`, `yaw_rate`, `position_source_code`, `position_source`, `wind_speed`, `wind_direction_code`, `wind_direction`, `home_offset_north`, `home_offset_east`
  - [`Camera`](#camera-type-25): `is_connected`, `is_usb_connected`, `is_time_synced`, `photo_state`, `record_state`, `sd_card_total_mb`, `sd_card_free_mb`, `remaining_photos`, `remaining_video_seconds`, `record_time`, `camera_type`, `camera_model`
  - [`Gimbal`](#gimbal-type-3): `joint_pitch`, `is_resetting`
  - [`Home`](#home-type-2): `has_go_home`, `aircraft_flight_count`
  - [`MCParams`](#mcparams-type-19): `mvo_func_enabled`, `avoid_obstacle_enabled`, `user_avoid_enabled`
  - [`RCDisplayField`](#rcdisplayfield-type-62): `right_dial`, `is_shutter_half_pressed`, `is_shutter_pressed`, `is_record_pressed`, `is_custom_button_1_pressed`, `is_custom_button_2_pressed`
  - [`AppGPS`](#appgps-type-14): `altitude` (renamed from `horizontal_accuracy`)
  - [`SmartBatteryGroup`](#smartbatterygroup-type-22): `static.manufacture_date` (replaces `static.temperature`), `dynamic.remaining_energy`, `dynamic.is_truncated`, `single_voltage.is_truncated`
  - [`VisionGroup`](#visiongroup-type-17): `vert_low_limit_active`, `avoidance_flags`
  - [`ADSBFlightData`](#adsbflightdata-type-26): `aircraft[]` gains `warning_level`, `altitude_type`, `relative_altitude`, `vertical_trend`, `distance`
  - [`Firmware`](#firmware-type-15): `entries` (`[{ sender_type, sender_name, sub_sender_type, version, full_version }]`)
- Removed: `VisionGroup` `is_braking`, `is_ascent_limited`, `is_avoid_active_obstacle` and `is_landing_confirmation_needed` (no supported source).
- Nested values (`SmartBatteryGroup` `static` / `dynamic` / `single_voltage`, `ADSBFlightData.aircraft`, `VisionGroup.detections`) are JSON objects instead of Python repr strings.
- Values fixed without a key change: `SmartBattery` (type 8), the `Camera` status bits, `MCParams.fail_safe`, the `Home` and `Gimbal` bits, `FlightControllerCommonOSD.need_go_home_time` (`null` instead of 65535) and `OSD.drone_type` (names for seven more aircraft).

**API and CLI** (see [Python API](#python-api))

- `--extended` now works; in 0.2.1 the option existed but did nothing.
- `records_to_frames(records, details=None, extended=False, version=None)`: `extended=True` sets `Frame.extended` and adds the extended keys to `Frame.to_dict()`; `version` lets the cell count come from the dynamic battery records. `parse_file()` and `DJILog.frames()` pass the version but have no `extended` option.
- New in `frame.models`: `Frame.extended`, `Frame.snapshot()`, `FrameRC.release_buttons()`, an `extended` argument on the section `to_dict()` methods, and the classes `FrameExtended`, `FrameRTK`, `FrameAirLink`, `FrameNavigation`, `FrameAppHud`, `FrameHudWarning`, `FrameSecondaryGimbal` and `FrameBatteryPack`. `FrameAppGPS.horizontal_accuracy` is now an alias property, no longer a constructor argument.
- New in `frame.builder`: `battery_layout()` with `BatteryLayout`, `is_valid_dynamic()`, `has_fc_common_osd()` and `main_gimbal_stream()`. The record modules gain enums and helpers for the new fields (for example `RTKSolutionType`, `LinkWorkMode`, `PhotoState`, `DeviceType`, `camera_model_name()`), and `decoder.protobuf` is a small schema-less protobuf reader.
- `DJILog.records()` also warns for keychains that hold no key, such as `[{}]`.
- CSV, GeoJSON and KML exports are unchanged: they carry none of the new fields, also with `--extended`.

Not new in 0.3.0: the decryption of records 253 and 254 in the app-message key chain (which fixed garbled app messages and `custom.dateTime`, see [App Messages](#app-messages)), the key mapping of v14 record type 57 and the keychain department fallback for Mobile SDK logs came with builds of 0.2.1 from late October 2026.

## Extracted Data Reference

Every frame (emitted at ~10 Hz) contains the following data groups. The summary is emitted once per flight by `parse_file()`; keys after `productType` appear only when the log carries the value (`cameraModel` can be `null`). Some values from the records are range-checked: a value outside the range given in its row counts as unknown.

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
| `cameraType` | int | DJI payload type code of the main camera (e.g. 43 Zenmuse H20T, 61 H20N, 83 H30T, 53 Matrice 30T, 99 Matrice 4TD), from the first camera record long enough to carry it |
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
| `isStuck` | bool | Gimbal stuck. Read from bit 0x40 since 0.3.0 (0x20, read before, is the install direction); never set in our logs |

`gimbal.yaw` differs from true north by an offset. The offset stays about the same for a power cycle on M300, M350, M30 and Neo 2, but can move by tens of degrees on M4TD, Mini 5 Pro, Mavic Mini and Neo. Do not use it as the camera bearing. Use `osd.yaw` + `gimbal.yawRelativeToAircraft` (`--extended`) on M300, M350, M30 and Mavic Mini, and `osd.yaw` alone on the other aircraft.

On Matrice 4TD airframes with a top accessory (most likely the AL1 spotlight), the gimbal records interleave two devices. `gimbal` follows the camera gimbal only: the device whose roll stays level, as a camera gimbal keeps the horizon. The accessory is in `secondaryGimbal` with `--extended`. Versions of the parser before 0.3.0 mixed the two, so on those airframes `gimbal` often showed the accessory: roll followed the aircraft instead of staying level, and the pitch-endpoint tip was repeated. Pitch was mostly unaffected, because the accessory tilts with the camera, except that it stops at +35° when the camera tilts higher.

### Camera

| Field | Type | Description |
|---|---|---|
| `isPhoto` | bool | `true` in a frame that received a camera record reporting a photo capture (single, burst, HDR or panorama). Camera records arrive about once a second, and unlike the other camera fields this flag is reset every frame, so a long capture shows up about once a second. It is not a photo count |
| `isVideo` | bool | Video recording active (raw `record_state` not 0) |
| `sdCardIsInserted` | bool | SD card present |
| `sdCardState` | string | SD card state (`Normal`, `NotInserted`, `Full`, `Slow`, `SuggestFormat`, `Repairing`, `BecomeSlow`, ...) |

Versions of the parser before 0.3.0 read these four fields from the wrong bits. On v14 logs `isPhoto` was `true` in every frame that received a camera record (about one in ten), `isVideo` was fixed per aircraft model (`true` on M30/M300/M350/M400, `false` on M4TD and consumer drones), `sdCardIsInserted` was almost always `false`, and `sdCardState` was usually `Invalid` (`IllegalFileSystem` on most M300 logs). None of them reflected the real camera state.

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
| `isBeginnerMode` | bool | Beginner mode active. Read from the right bit since 0.3.0; never set in our logs |
| `isIocEnabled` | bool | Intelligent Orientation Control (course lock / home lock) switched on, per the upstream name. Read from the right bit since 0.3.0; never set in our logs |
| `goHomeHeight` | int | Go-home altitude (meters) |
| `maxAllowedHeight` | float | Regulatory max height (meters) |

### App GPS — Controller/Phone Position

| Field | Type | Description |
|---|---|---|
| `latitude` / `longitude` | float | Controller/phone GPS position (degrees) |
| `altitude` | float | Controller/phone altitude (meters), in the same vertical reference as the aircraft's GNSS heights. `null` until the first record. New in 0.3.0 |
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

Parser builds from before 28 October 2026 (still version 0.2.1) skipped two internal v14 record types (253 and 254) instead of decrypting them. These records share a key chain with the app messages and the Custom record that sets `custom.dateTime`. The first 16 bytes of the next record in that chain were then garbled. In the 70 v14 logs we have:
- About one in ten app messages started with unreadable characters, and some were empty.
- `custom.dateTime` was wrong in about 15% of frames, with dates hundreds or thousands of years off that jumped back and forth.

Both have been correct since then. 0.3.0 also parses record 253 (`KeyValueSnapshot` in raw output); record 254 is still decrypted but not emitted.

### Changes to default values

Versions of the parser before 0.3.0 read some default frame values from the wrong bytes or the wrong records. In the 74 logs we can decrypt (70 v14, 4 v12), these values change (the last item is about logs parsed without keys):
- `battery.chargeLevel` and `battery.voltage` on M300, M350 and Mavic Mini: the SmartBattery record (type 8) was read one byte off, so it gave the low-battery warning threshold (20–30%) as `chargeLevel` and a wrong `voltage` (about 5–24 V). On M300, M350 and the one Mavic Mini log that also has SmartBatteryGroup dynamic records, these values alternated with the real ones. On the other three Mavic Mini logs type 8 was the only battery source, so `chargeLevel` was the threshold and `voltage` was wrong (16–22 V for a 7.4–7.9 V pack) in every frame.
- `battery` on M30, M300 and M350: the values came from pack 1 only. They are now the aggregate of both packs (see Battery), so `currentCapacity`, `fullCapacity` and `current` are about twice the old values. In the first frames of some logs, before the first aggregate record, these three are now 0 (see Battery).
- `battery.cycleCount` and `battery.designedCapacity`, and the summary keys `batteryCycleCount` and `batteryDesignedCapacity`, were missing in the 11 of 27 dual-battery logs that only log pack 2. They are now set from pack 2. Like the pack-1 values in the other dual-battery logs, they cannot be matched to `batterySn` or `batterySns` (see Summary).
- `flightController.batteryPercentNeededToGoHome` on M30, M400, M4TD, Mini 5 Pro, Neo and Neo 2 was 0 while the type-63 record had no go-home estimate. It is now `null` there (see Flight Controller): 6,893 of 738,677 frames in 30 of our 74 logs, most of them on Neo 2 and Neo. The CSV cell is empty in those frames.
- `battery.cellNum` and `battery.cellVoltages`: the cell count came from a product table that does not know the newer aircraft and gave 4. It now comes from the log: 13 on M400, 6 on M4TD, 2 on Mini 5 Pro, Neo and Neo 2. Cell records with a 2-byte header and the truncated M4TD records were also misread. Together this gave `maxCellVoltageDeviation` values up to 4.1 V on M4TD, Mini 5 Pro, Neo and Neo 2, and 8.7 V and 63 V in one M300 and one M350 log, where a single misread cell record stayed in place for the whole flight.
- `flightController` on M300, M350 and Mavic Mini was always `null`. It is now filled from the type-8 record (see Flight Controller).
- `camera.isPhoto`, `camera.isVideo`, `camera.sdCardIsInserted` and `camera.sdCardState` were read from the wrong bits (see Camera).
- `gimbal` on Matrice 4TD airframes with a top accessory often showed the accessory instead of the camera gimbal, and `app.tip` repeated the gimbal pitch-endpoint tip there while the camera gimbal was at its pitch limit (see Gimbal).
- `vision.collisionAvoidanceEnabled` was always `false`, because the VisionGroup record (type 17) was split at the wrong place. It now shows the obstacle-avoidance setting. `vision.isBraking`, `vision.isAscentLimited` and `vision.isLandingConfirmationNeeded` are now always `false` (see Vision).
- `osd.droneType` was a number for seven aircraft and is now a name: 53 `MavicMini`, 67 `Matrice30`, 100 `Matrice4D`, 103 `Matrice400`, 104 `Neo`, 112 `Mini5Pro`, 124 `Neo2`.
- `gimbal.isStuck`, `home.isBeginnerMode` and `home.isIocEnabled` now read the right bits. None of them is set in any of our logs, so no value changed there.
- The summary of a v13 or v14 log parsed without keys (or with keychains that hold no key) used to contain values read from the still-encrypted records. In a check on 50 of our v14 logs parsed without keys, 0.2.1 gave `firmwareVersions` made from noise in all 50, a `batteryCycleCount` in 45 and `componentSerials` in 6, and in 21 logs whose header has no camera serial it took `cameraSn` from the garbled Recover record. The summary now has only the 15 header keys (see Summary), so the keys added in 0.3.0, such as `cameraType`, are left out too.

Values derived from these (`minTemperature`, `maxTemperature`, the cell deviations, `isCellVoltageEstimated`) change with them; no other default key changed value in our logs. `appGps.altitude` is a new key. `appGps.horizontalAccuracy` and `nearbyAircraft[].altitude` keep their values but were documented wrongly: the first is the controller altitude, the second is in meters, not feet. The CSV export has the same columns as before.

### Extended sections (`--extended` only)

With `--extended` (or `records_to_frames(..., extended=True)`), each frame also gets five sections with data that the default output leaves out, and the default sections get extra keys (listed after the five sections). Values carry forward between records and are `null` until the first record of that kind arrives. Aircraft that never write a record type (for example enterprise aircraft and type 54) still get that section or key, with the value `null`. Without the flag, frames have only the default keys. `parse_file()` and `DJILog.frames()` have no option for extended frames, and the CSV, GeoJSON and KML exports leave the extended keys out.

#### Section `rtk`

RTK/GNSS module status from the `RTKDifference` record (type 45, 1 Hz). M30, M300, M350, M400 and M4TD; `null` on the other aircraft.

| Field | Type | Description |
|---|---|---|
| `positionSolution` | string | `NONE`, `Single`, `Float`, `Fixed`, `Code52` (undocumented, M400 only; not shown to be precise) or `UNKNOWN` |
| `positionSolutionCode` | int | Raw solution code (0 / 16 / 34 / 50 / 52) |
| `latitude` / `longitude` | float | RTK antenna 1 position (degrees) |
| `height` | float | RTK antenna height (m); likely ellipsoidal, not relative to take-off |
| `stdLatitude` / `stdLongitude` / `stdAltitude` | float | 1-sigma error north / east / vertical (m); the axis order is plausible but not verified |
| `satellites` | int | Satellites tracked by receiver 1 (all constellations). On M400 and M4TD it includes a fifth constellation that has no key of its own, so the four keys below need not add up to it |
| `gpsSatellites` / `beidouSatellites` / `glonassSatellites` / `galileoSatellites` | int | Receiver-1 satellites per constellation. The GPS and BeiDou labels are confirmed, GLONASS and Galileo are plausible |
| `hasBase` | bool | The record carries a base position: corrections from a base / network station |
| `correctionAge` | float | Age of the corrections (s); 0 = no corrections |
| `dualAntennaHeading` | float | Dual-antenna baseline heading (degrees, 90° off the nose); `null` on single-antenna aircraft |

#### Section `airLink`

Radio link from the `AirLinkDataField` record (type 57, about 5 Hz). All v14 aircraft (M30, M300, M350, M400, M4TD, Mini 5 Pro, Neo, Neo 2); `null` on v12 logs. The 1 Hz/4 Hz sub-type-1 records update only `sdrQuality`.

| Field | Type | Description |
|---|---|---|
| `sdrLinkUp` / `lteLinkUp` | bool | OcuSync (SDR) and 4G/LTE (DJI Cellular) link connected |
| `sdrQuality` / `lteQuality` | int | Link quality 0–5 (0 = no usable signal; use `sdrLinkUp` for link up/down) |
| `linkQuality` | int | Fused 0–5 level shown in the pilot app |
| `workMode` | string | `SdrOnly`, `SdrLte` (LTE-enhanced transmission enabled) or `UNKNOWN` |
| `lteLevelA` / `lteLevelB` | int | The two LTE side levels 0–5 (probably aircraft and RC side; not verified) |

#### Section `navigation`

Flight-controller navigation state from the `AgricultureGroundStationPush` record (type 48, 10 Hz). M30, M300, M350, M400 and M4TD; `null` on the other aircraft. Records that repeat an earlier aircraft-clock timestamp (a few replayed records on M4TD/M400) are skipped.

| Field | Type | Description |
|---|---|---|
| `aircraftClock` | float | Aircraft clock (s, Unix-like). Not uniformly UTC: UTC + 1 h on M30/M300/M350, UTC or UTC + 18 s on M4TD/M400 |
| `satellitesUsed` | int | Satellites in the position solution in use |
| `distanceToHome` | float | Horizontal distance to the home point (m) |
| `isRtkFixed` | bool | Flight controller navigates on an RTK fixed solution |
| `relativeHeight` | float | Height above take-off at full precision (m) |
| `gnssHeight` | float | Standalone GNSS height (m) |
| `geoidUndulation` | float | Geoid separation at home (m); `null` when unavailable |

#### Section `appHud`

DJI Fly on-screen notifications from the `GOBusiness` record (type 54). Consumer aircraft only (Mavic Mini, Mini 5 Pro, Neo, Neo 2); always `null` on enterprise aircraft. A record changes only the parts it flags, so each key is `null` until the first update of its part. Texts follow the app's UI language: key on codes, not text.

| Field | Type | Description |
|---|---|---|
| `statusBar` / `statusBarLevel` | string / int | Top status label (e.g. "In flight") and severity 1–3 |
| `tip` / `tipCode` | string | Current pop-up tip and its app code (decimal string); `null` again once the app clears the tip |
| `warnings` | array | Active warnings `[{ text, code, level }]`; `code` is the `(Code: X)` suffix (decimal, or 8 hex digits for HMS codes) and `level` the severity (2–3 seen, same scale as `statusBarLevel`). `[]` once the app reports an empty list |

#### Section `secondaryGimbal`

A second gimbal device in the gimbal records (record type 3). Seen only on Matrice 4TD airframes with a top accessory, most likely the AL1 spotlight. It tilts in pitch only, and its pitch and yaw follow the camera gimbal, with a stop at +35° (seen in the one log where the camera tilted higher). Its roll follows the aircraft. On all other aircraft, and on a Matrice 4TD without an accessory, the section is present but every field is `null`.

| Field | Type | Description |
|---|---|---|
| `pitch` / `roll` / `yaw` | float | Angles (degrees) |
| `isPitchAtLimit` | bool | Pitch axis at its limit (same flag as in `gimbal`). Never set in the logs we have, not even while the accessory sits at its +35° stop |

**Extra keys in the default sections.** They are added after the default keys of each section.

#### Extra keys in `osd`

From the OSD record (type 1). The record is 56 bytes on v12, 68–71 bytes on M30/M300/M350 and 84–85 bytes on M400, M4TD, Mini 5 Pro, Neo and Neo 2; keys whose bytes lie beyond the end of the record are `null`.

| Field | Type | Description |
|---|---|---|
| `windSpeed` | float | Wind speed estimated by the aircraft (m/s); 0 = calm or no estimate. `null` on v12 logs, and when the record reads 255 (no value; seen only in records that were not decrypted) |
| `windDirection` | string | Direction the wind blows from: `N`, `NE`, `E`, `SE`, `S`, `SW`, `W` or `NW`; `null` when calm, when `windSpeed` is `null`, and on v12 logs |
| `positionSource` | string | Positioning source of the flight controller: `None`, `Vision`, `GNSS` or `RTKFixed` (`Unknown(n)` for other codes). `null` on v12 logs |
| `positionSourceCode` | int | Raw code (0–3 in our logs); `null` on v12 logs |
| `yawRate` | float | Yaw rate (deg/s, positive = clockwise seen from above). All logs, v12 included |
| `homeOffsetNorth` / `homeOffsetEast` | float | Position relative to the home point (m, north and east). M400, M4TD, Mini 5 Pro, Neo and Neo 2 only; `null` without a GNSS fix |

#### Extra keys in `battery`

| Field | Type | Description |
|---|---|---|
| `stateOfHealth` | int | State of health (%) from the static battery record (same pack as `cycleCount`); `null` when the battery reports 0 (unknown; always on Mini 5 Pro) and before the static record |
| `remainingEnergy` | float | Remaining energy (Wh), the battery's own estimate. M30, M400, Mini 5 Pro, Neo and Neo 2 only; `null` on the other aircraft and, on M30, until the aggregate record arrives |
| `lowWarningThreshold` / `criticalWarningThreshold` | int | Low and critical battery warning levels set by the pilot (%), from the OSD record; `null` until the first non-zero value |
| `packs` | array | Dual-battery aircraft only (M30, M300, M350): `[{ index, chargeLevel, voltage, current, currentCapacity, fullCapacity, temperature }]` for packs 1 and 2 (`index` 1 or 2; %, V, A, mAh, mAh, °C), from the latest record of each pack. `null` on single-battery aircraft |

#### Extra keys in `gimbal`

From the camera gimbal only. `null` before the first gimbal record.

| Field | Type | Description |
|---|---|---|
| `yawRelativeToAircraft` | float | Gimbal yaw relative to the aircraft heading (degrees). Meaningful on M300, M350, M30 and Mavic Mini. It does not behave as a joint angle on M4TD and Mini 5 Pro, and is always 0 on Neo and Neo 2 |
| `jointPitch` | float | Gimbal pitch relative to the airframe (degrees); `null` when the gimbal record is shorter than 22 bytes |
| `isResetting` | bool | A gimbal reset (recenter or point down) was in progress in a record of this frame |

#### Extra keys in `camera`

| Field | Type | Description |
|---|---|---|
| `workMode` | int | 0 photo, 1 video, 2 playback, 7 new playback |
| `sdCardTotalMb` / `sdCardFreeMb` | int | Storage size and free space (MB) |
| `remainingPhotos` | int | Photos that still fit |
| `remainingVideoSeconds` | int | Video time that still fits (s) |

The four storage keys are `null` when the camera reports a total of 0 (Mavic Mini, one M350 log) or the camera record is too short to carry them.

#### Extra keys in `rc`

From the RC display record (type 62); `null` in logs without it, such as Mavic Mini.

| Field | Type | Description |
|---|---|---|
| `isShutterHalfPressed` / `isShutterPressed` | bool | Shutter button half / fully pressed |
| `isRecordPressed` | bool | Record button pressed |
| `isCustomButton1Pressed` / `isCustomButton2Pressed` | bool | C1 / C2 button pressed (the pilot sets their function) |
| `leftDial` / `rightDial` | int | Dial positions on the stick scale (364–1684, centre 1024). The left dial tilts the gimbal. The right dial pans it on M300/M350, has no gimbal effect on M4TD and stays at about 1024 on Neo and Neo 2 |

The buttons are momentary: `true` when a record in the frame had the button down.

#### Extra keys in `vision`

| Field | Type | Description |
|---|---|---|
| `isNearGround` | bool | Ground within the range of the downward sensors (raw `vert_low_limit_active`). `null` before the first VisionGroup record and in logs without one |

#### Extra keys in `flightController`

`timeNeededToGoHome` and `timeNeededToLand` come from the same records as the default keys (type 63, or type 8 on M300, M350 and Mavic Mini); `rcLostAction` comes from the MCParams record (type 19).

| Field | Type | Description |
|---|---|---|
| `timeNeededToGoHome` | int | Estimated time to fly home (s); `null` while the aircraft reports no estimate (type 63 time 65535). On M300, M350 and Mavic Mini `null` until its first non-zero value; it stays `null` on Mavic Mini |
| `timeNeededToLand` | int | Estimated time to land from the current height (s). `null` before the first source record; on M300, M350 and Mavic Mini until its first non-zero value |
| `rcLostAction` | string | Action when the RC signal is lost: `Hover`, `Landing` or `GoHome`. `null` before the MCParams record and for unknown codes |

#### Extra keys in `nearbyAircraft[]`

| Field | Type | Description |
|---|---|---|
| `distance` | int | Horizontal distance from the aircraft (m) |
| `relativeAltitude` | int | Traffic altitude minus aircraft altitude (m; positive = traffic above) |
| `verticalTrend` | string | `Level`, `Rising` or `Falling`; `null` for other codes |
| `warningLevel` | int | AirSense warning level: 1 tracked, 2 caution, 3 and up take action (only 1 and 2 seen) |
| `altitudeType` | string | Reference of `altitude`: `Ellipsoid` (WGS84; M400, M4TD) or `MSL` (M350); `null` for other codes |

### Raw output (`--raw`)

`--raw` writes every parsed record as `{ "type": ..., "content": { ... } }`, where `type` is the record type name and `content` holds the record's fields under their Python names. Enum values appear as their names and byte fields are left out. Since 0.3.0 nested values (for example `ADSBFlightData.aircraft`, `SmartBatteryGroup` and `VisionGroup.detections`) are emitted as JSON objects instead of Python repr strings. Payloads that cannot be recognised, such as records left encrypted when a key is missing, stay out of the raw output.

Raw output for a v14 enterprise log is about 40–55% larger than before; type 48 alone runs at 10 Hz. `KeyValueSnapshot` adds only one to five records per log.

Raw output holds identifying data: serials (`Recover`, `ComponentSerial` and now `KeyValueSnapshot`), aircraft, home and pilot positions (OSD, Home, AppGPS, and now `RTKDifference` and `AgricultureGroundStationPush` at full precision) and wall-clock times (`Custom.update_timestamp`, and now `KeyValueSnapshot.timestamp` and the aircraft clock in `AgricultureGroundStationPush.timestamp`). Handle it like the log file itself.

#### New record types

The seven record types below are new in 0.3.0. `RTKDifference`, `AgricultureGroundStationPush`, `AirLinkDataField` and `GOBusiness` also feed the extended sections; `GSMissionStatus`, `Security` and `KeyValueSnapshot` appear only in raw output (the summary takes `batterySns` and `accessorySn` from `KeyValueSnapshot`).

##### `RTKDifference` (type 45)

RTK/GNSS module status, about once a second, with no timestamp of its own. M30, M300, M350, M400 and M4TD (57 of our logs). Records are 80 bytes on M30/M300/M350 and 83 bytes on M400/M4TD; the 83-byte layout adds the `*_gnss5_sats` counters. Source of the extended [`rtk`](#section-rtk) section.

| Field | Type | Description |
|---|---|---|
| `position_solution` | string | Position solution: `NONE`, `Single`, `Float`, `Fixed`, `Code52` (undocumented, M400 only) or `UNKNOWN` |
| `position_solution_code` | int | Raw solution code (0 / 16 / 34 / 50 / 52; other codes are kept) |
| `rx1_gps_sats` / `rx1_beidou_sats` / `rx1_glonass_sats` / `rx1_galileo_sats` | int | Satellites tracked by receiver 1 (antenna 1) per constellation. The GPS and BeiDou labels are confirmed, GLONASS and Galileo are plausible |
| `rx1_gnss5_sats` | int | Receiver-1 satellites of a fifth constellation; which system it is is not known. 0 in 80-byte records |
| `rx2_gps_sats` / `rx2_beidou_sats` / `rx2_glonass_sats` / `rx2_galileo_sats` / `rx2_gnss5_sats` | int | The same for receiver 2 (second antenna); 0 on single-antenna aircraft |
| `base_gps_sats` / `base_beidou_sats` / `base_glonass_sats` / `base_galileo_sats` / `base_gnss5_sats` | int | The same for the base (reference) side; 0 without a base |
| `rover_latitude` / `rover_longitude` | float | RTK antenna 1 position (degrees) |
| `rover_height` | float | RTK antenna 1 height (m); not relative to take-off, most likely ellipsoidal (not verified) |
| `has_base` | bool | The record carries a base position |
| `base_latitude` / `base_longitude` | float | Base position (degrees); `null` without a base |
| `base_param_47` | int | Opaque 32-bit value, non-zero only with a base; meaning not verified |
| `dual_antenna_heading` | float | Dual-antenna baseline heading (degrees, 90° off the nose); `null` when `heading_solution_code` is 0 |
| `heading_solution` / `heading_solution_code` | string / int | Solution type of the heading, same codes as `position_solution`; 0 / `NONE` on single-antenna aircraft |
| `correction_age` | float | Age of the RTK corrections (s); 0 = no corrections. `null` in records shorter than 80 bytes |
| `std_latitude` / `std_longitude` / `std_altitude` | float | 1-sigma position error north / east / vertical (m); the axis order is plausible but not verified. `null` in records shorter than 80 bytes |
| `reserved_0` | int | Byte 0; always 0 in our logs |
| `flag_56` | int | Byte 56; always 1 in our logs; meaning not known |
| `length` | int | Record length in bytes (80 or 83) |

##### `AgricultureGroundStationPush` (type 48)

Despite DJI's name, a 71-byte flight-controller navigation state written about once per OSD record (10 Hz) by M30, M300, M350, M400 and M4TD (57 of our logs). A few M4TD/M400 records are exact replays of an earlier record (same `timestamp_sec` and `timestamp_nsec`), and in about half the logs the last one or two records re-zero `relative_height`. Source of the extended [`navigation`](#section-navigation) section.

| Field | Type | Description |
|---|---|---|
| `latitude` / `longitude` | float | Fused aircraft position (degrees; stored as radians) |
| `relative_height` | float | Height above take-off (m), unrounded |
| `yaw` | float | Heading (degrees, -180 to 180, 0 = north) |
| `rtk_flag_a` | int | RTK-related flag, constant per flight; meaning not verified |
| `is_rtk_fixed` | bool | The flight controller navigates on an RTK fixed solution |
| `timestamp_sec` / `timestamp_nsec` | int | Aircraft clock: whole seconds and nanoseconds |
| `timestamp` | float | `timestamp_sec + timestamp_nsec / 1e9` (s). Not uniformly UTC: UTC + 1 h on M30/M300/M350, UTC or about UTC + 18 s on M4TD/M400 |
| `nav_status_flags` | int | Navigation status bitfield; 0x44 marks RTK fixed, the other bits are not known |
| `satellites_used` | int | Satellites in the solution in use |
| `home_latitude` / `home_longitude` | float | Home point (degrees) |
| `takeoff_reference_height` | float | GNSS-frame height that `relative_height` counts from (m) |
| `distance_to_home` | float | Horizontal distance to the home point (m) |
| `fc_altitude` | float | Flight-controller altitude (m). Its reference changes when RTK fixes, so do not treat it as one series across an `is_rtk_fixed` change |
| `gnss_height` | float | Standalone GNSS height (m; updates at about 5 Hz) |
| `geoid_undulation` | float | Geoid separation (m), constant per flight; `null` when the record reads 0 |
| `rtk_state_b` | int | 1 by default, 2 only under an RTK fix; meaning not verified |

##### `AirLinkDataField` (type 57)

Radio-link status, written by all v14 aircraft (70 of our logs; v12 logs have a different, unknown layout and it is not decoded there). Sub-type 1 (3 bytes; 1 Hz on M400, M4TD, Mini 5 Pro, Neo and Neo 2, 4 Hz on M30, M300 and M350) sets only `sdr_quality`; every field except `sub_type`, `length` and `sdr_quality` is `null`. Sub-type 2 (about 5 Hz; 26 bytes on M30/M300/M350, 35 bytes on the other aircraft) sets the rest. Levels are bars 0–5, where 0 means no usable signal. The truncated record at the end of every v14 log is not emitted. Source of the extended [`airLink`](#section-airlink) section.

| Field | Type | Description |
|---|---|---|
| `sub_type` | int | 1 (SDR level) or 2 (link status) |
| `length` | int | Record length in bytes |
| `sdr_quality` | int | OcuSync (SDR) quality 0–5, the lower of the uplink and downlink bars. In sub-type 2 it repeats the latest sub-type-1 value. 0 is not "link down": use `sdr_link_up` |
| `sdr_link_up` / `lte_link_up` | bool | SDR and 4G/LTE (DJI Cellular) link connected |
| `lte_quality` | int | LTE quality 0–5, the lower of `lte_level_a` and `lte_level_b` |
| `link_quality` | int | Fused 0–5 level shown in the pilot app |
| `link_work_mode` / `link_work_mode_code` | string / int | `SdrOnly` (1) or `SdrLte` (3, LTE-enhanced transmission); `UNKNOWN` for other codes |
| `lte_level_a` / `lte_level_b` | int | The two LTE side levels 0–5, probably aircraft and RC side (not verified) |
| `aux_level_1hz` | int | A 0–5 level from a separate 1 Hz source; meaning not verified |
| `unknown_11` | int | Byte 11; meaning not known |
| `layout_code` | int | 1 on the 26-byte layout, 3 on the 35-byte layout |
| `channel_like_19` | int | Signed byte 19, 26-byte layout only; possibly the SDR channel (not verified) |
| `lte_fusion` | bool | 35-byte layout only; `true` exactly when `link_work_mode` is `SdrLte` |
| `const_29` | int | 35-byte layout only; 1 or 3, constant per log; meaning not known |

##### `GOBusiness` (type 54)

The DJI Fly app's on-screen notification state, stored as protobuf without a published schema. Written only by DJI Fly consumer aircraft: Mavic Mini, Mini 5 Pro, Neo and Neo 2 (17 of our logs, v12 included; in v12 logs the parser also recovers records whose length overflowed the one-byte length field). Each record updates at most one of three parts, marked by its `*_updated` flag; parts without the flag are unchanged. A separate record, once per log, carries only `flag_8` and `value_9`. Texts follow the app's UI language. Source of the extended [`appHud`](#section-apphud) section.

| Field | Type | Description |
|---|---|---|
| `ui_marker` | int | Protobuf field 1: 1 on every notification update, 0 in the once-per-log record and in empty records |
| `status_bar_updated` | bool | The record updates the status bar |
| `status_bar.text` / `status_bar.level` | string / int | Top status label (for example "In flight") and its severity (1–3 seen, higher = more severe). `status_bar` is `null` when the record does not carry it |
| `tip_updated` | bool | The record updates the tip; with `tip` `null` the tip slot is now empty |
| `tip.text` / `tip.code` | string | Pop-up tip and its app event code (decimal string) |
| `tip.level` | int | Tip level (0–2 seen); meaning not verified |
| `tip.duration_ms` | float | Nominal display time (ms) |
| `warnings_updated` | bool | The record carries a full snapshot of the active warning list; with an empty `warnings` the list is now empty |
| `warnings[].text` / `warnings[].code` / `warnings[].level` | string / string / int | One active warning: its text, the code from its `(Code: X)` suffix (decimal, or 8 hex digits for HMS codes) and its level (2–3 seen, same scale as the status bar) |
| `flag_8` / `value_9` | int | Fields 8 and 9 of the once-per-log record; meaning not known |
| `is_complete` | bool | The protobuf parsed completely. Always `true` in raw output: a record that does not parse completely is not emitted |

##### `GSMissionStatus` (type 32)

Legacy ground-station mission status (Waypoint 1.0, Hotpoint, Follow Me, course/home lock), 7 bytes at about 10 Hz. Written by M30, M300 and M350 (26 of our logs). Every byte has been 0 in all our logs, also during DJI Pilot 2 waypoint missions, so the field layout, which comes from public references, is not verified. Use `osd.flycState` and `osd.flightAction`, not this record, to detect waypoint missions. Raw output only.

| Field | Type | Description |
|---|---|---|
| `raw_hex` | string | The 7 record bytes as hex |
| `has_content` | bool | Any byte is non-zero; never seen |
| `mission_type` | string | Byte 0 as `NONE`, `Waypoint`, `Hotpoint`, `FollowMe`, `CourseHomeLock`, `TBD` or `UNKNOWN` (not verified) |
| `trailing_flag` | int | Byte 6 (not verified) |

Bytes 1–5 (the per-mission data) are only in `raw_hex`.

##### `Security` (type 55)

An opaque 256-byte block, written once per 10 OSD records in every v14 log (70 of our logs). The log has no key for it, and the block is not AES output (it may be an RSA-2048 ciphertext or signature, which is not proven), so it cannot be decoded. Only two diagnostics are exposed; the block itself is not in the JSON. Raw output only.

| Field | Type | Description |
|---|---|---|
| `check_ok` | bool | The XOR check byte after the block equals `(seed + 55) & 0xFF` for the record's XOR seed; `null` when the seed is unknown |
| `in_range` | bool | The block's top 16 bits are within the bound seen in our logs (0xC773) |

##### `KeyValueSnapshot` (type 253)

A key/value snapshot that the app writes when it connects to the aircraft, in v14 logs only (70 of our logs). A log has one or two records at the start, and up to five when the app reconnects during the flight. Only two module/key pairs occur. Record 254, which holds values re-sent on change (mostly wind), is decrypted but not emitted. Raw output only; the summary takes `batterySns` and `accessorySn` from it.

| Field | Type | Description |
|---|---|---|
| `module` / `key` | int | Module and key id from the record header: 7/1 (component serials) or 5/1 (flight time) |
| `timestamp` | string | App wall clock when the snapshot was written (ISO 8601, UTC); `null` when the record has none |
| `serials` | object | Module 7 key 1: component serials keyed by protobuf field number (a string in JSON). `"1"` matches the camera serial, `"6"` is an accessory (M4TD only), `"7"` and `"8"` are battery slots 1 and 2, and the role of `"2"` is not known. Empty for module 5 and on Mini 5 Pro, Neo and Neo 2 |
| `total_flight_time` | float | Module 5 key 1: a total accumulated flight time (s) whose owner (aircraft, RC or app) is not known; it steps up by the current flight's time when re-sent during the log. `null` for module 7. Enterprise aircraft only |

#### Changes in existing records

Renamed or removed keys: `OSD.battery` is now `sequence_counter`, `AppGPS.horizontal_accuracy` is now `altitude`, `SmartBatteryGroup` static `temperature` is now `manufacture_date`, and `VisionGroup` loses `is_braking`, `is_ascent_limited`, `is_landing_confirmation_needed` and `is_avoid_active_obstacle`. Details per record:

##### `OSD` (type 1)

Byte 40 (`sequence_counter`, was `battery`) is a rolling counter that steps by about 5 per record, not battery data. `drone_type` is a name for seven more aircraft (see `droneType` above). The new fields are set only when the record is long enough (see [the extended `osd` keys](#extra-keys-in-osd)); otherwise they are `null`.

| Field | Type | Description |
|---|---|---|
| `sequence_counter` | int | Rolling counter (byte 40); was `battery` |
| `low_battery_warning` / `critical_battery_warning` | int | Low and critical battery warning levels set by the pilot (%); the same bytes as SmartBattery `low_warning` / `serious_low_warning` |
| `low_battery_warning_go_home` / `critical_battery_warning_landing` | bool | The action flags of the two levels: go home at the low level, land at the critical level |
| `yaw_rate` | float | Yaw rate (deg/s, positive = clockwise seen from above) |
| `position_source_code` / `position_source` | int / string | Positioning source: 0 `None`, 1 `Vision`, 2 `GNSS`, 3 `RTKFixed`, `Unknown(n)` for other codes; `null` on v12 |
| `wind_speed` | float | Wind speed estimated by the aircraft (m/s); `null` on v12 and when the wind byte reads 255, which happens only in records that were not decrypted |
| `wind_direction_code` / `wind_direction` | int / string | Direction the wind blows from: 1–8 = `N`, `NE`, `E`, `SE`, `S`, `SW`, `W`, `NW`; 0 = calm (name `null`). Both `null` when `wind_speed` is `null` |
| `home_offset_north` / `home_offset_east` | float | Position relative to the home point (m); 0/0 while no home point is set; `null` in records shorter than 82 bytes (M30, M300, M350, v12) |

##### `Camera` (type 25)

The existing `Camera` fields change value in most v14 records, because they used to be read from the wrong bits: `is_shooting_single_photo` (now photo state = single, was the connected bit), `is_recording` (now record state, was the USB bit), `is_storing` (now byte 2 bit 0x08, was byte 0 bit 0x08), `has_sd_card` (now byte 1 bit 0x02, was 0x10) and `sd_card_state` (now byte 1 bits 0x3C, was 0x0F; new states `SuggestFormat`, `Repairing` and `BecomeSlow`). `work_mode` is unchanged. New fields:

| Field | Type | Description |
|---|---|---|
| `is_connected` / `is_usb_connected` / `is_time_synced` | bool | Camera connected, USB connected (constant per platform in practice) and camera clock synced (byte 0 bits 0x01, 0x02, 0x04) |
| `photo_state` | string | `NONE`, `Single`, `Multiple`, `HDR`, `FullView` (panorama), `Other` or `UNKNOWN` |
| `record_state` | int | 0 idle, 2 recording; 1 and 3 appear for one record at the start and end of a recording |
| `sd_card_total_mb` / `sd_card_free_mb` | int | Storage size and free space (MB); a total of 0 means the camera reports no storage data |
| `remaining_photos` / `remaining_video_seconds` | int | Photos and video time (s) that still fit |
| `record_time` | int | Seconds since the recording started; unreliable, see below |
| `camera_type` / `camera_model` | int / string | DJI payload type code of the main camera and its model name (`null` for codes not in the table) |

The storage fields, `record_time`, `camera_type` and `camera_model` are `null` in records shorter than 24 bytes. `record_time` is unreliable on several enterprise aircraft: it stops at 30 s (15 s in some Matrice 4TD logs) and stays there until the recording ends. This happens in every Matrice 4TD and Matrice 400 log with a recording and in some Matrice 350 logs, so use `record_state` to tell whether a recording runs.

##### `Gimbal` (type 3)

| Field | Type | Description |
|---|---|---|
| `joint_pitch` | float | Pitch relative to the airframe (degrees); `null` in records shorter than 22 bytes |
| `is_resetting` | bool | A gimbal reset (recenter or point down) is in progress |

`yaw_angle` is the yaw relative to the aircraft heading (see `yawRelativeToAircraft`). `is_stuck` now reads bit 0x40 instead of 0x20; neither is set in our logs. `version` (low nibble of byte 11) tells the two devices apart on Matrice 4TD airframes with a top accessory: 2 is the camera gimbal and 1 the accessory in every such log we have.

##### `Home` (type 2)

| Field | Type | Description |
|---|---|---|
| `has_go_home` | bool | Home-state bit (byte 20 bit 0x80) with its upstream name; meaning not verified |
| `aircraft_flight_count` | int | Lifetime take-off counter of the aircraft; it goes up by one at the take-off record, so records before take-off do not include this flight (the summary `aircraftFlightCount` takes the last value). Only in 102-byte records (Mini 5 Pro, Neo 2); `null` otherwise |

`is_beginner_mode` and `is_ioc_open` now read the right bits (byte 21 bits 0x08 and 0x10; before, `is_beginner_mode` read the bit that is now `has_go_home`). None of these three bits is set in any of our logs.

##### `MCParams` (type 19)

The `fail_safe` names were swapped. Now 0 is `Hover`, 1 `Landing` and 2 `GoHome`, so logs that showed `Hover` now show `GoHome` and the other way round (63 of our 74 logs are `GoHome`).

| Field | Type | Description |
|---|---|---|
| `mvo_func_enabled` / `avoid_obstacle_enabled` / `user_avoid_enabled` | bool | Byte 1 bits 0x01, 0x02 and 0x04, named as in the upstream parser. `user_avoid_enabled` is the pilot's obstacle-avoidance switch; it matches `vision.collisionAvoidanceEnabled` in all 44 logs that have both records. The meaning of the other two is not verified |

They come after the old keys. The old keys `e_landing`, `go_home_altitude` and `dynamic_home_point` read the same three bits and always equal the new ones. They are misnomers, kept for compatibility, and will be removed in a later change of the raw format. In particular, `dynamic_home_point` is not the dynamic home point setting: that is `Home.is_dynamic_home_point_enabled` (`home.isDynamicHomePointEnabled`), which is off in all 74 of our logs, while bit 0x04 is set in 61.

##### `RCDisplayField` (type 62)

| Field | Type | Description |
|---|---|---|
| `right_dial` | int | Right dial on the stick scale (364–1684, centre 1024); `null` in records shorter than 19 bytes |
| `is_shutter_half_pressed` / `is_shutter_pressed` | bool | Shutter button half / fully pressed |
| `is_record_pressed` | bool | Record button pressed |
| `is_custom_button_1_pressed` / `is_custom_button_2_pressed` | bool | C1 / C2 button pressed |

`gimbal` is the left dial (the Python property `left_dial`).

##### `AppGPS` (type 14)

| Field | Type | Description |
|---|---|---|
| `altitude` | float | Pilot device altitude (m), in the same vertical reference as the aircraft's GNSS heights; was `horizontal_accuracy`. `null` in records shorter than 20 bytes (it used to read -1.0) |

##### `SmartBattery` (type 8)

`go_home_countdown` is one byte, not two, so `voltage`, `percent`, `low_warning`, `low_warning_go_home`, `serious_low_warning` and `serious_low_warning_landing` change value; they used to be read one byte off. `useful_time` is the remaining flight time (s), `go_home_time` / `land_time` are times needed (s), `go_home_battery` / `land_battery` the battery % needed, and `status` is the warning level (0 normal, 1 low, 2 critical). The meaning of `safe_fly_radius` and `volume_consume` is not verified. No key is added or removed.

##### `SmartBatteryGroup` (type 22)

`kind` is 1 (static), 2 (dynamic) or 3 (single cell voltages), and the matching object of `static`, `dynamic` and `single_voltage` is filled; the other two are `null`. Since 0.3.0 these objects are nested JSON instead of Python repr strings. `static.manufacture_date` replaces `static.temperature`, which was these bytes misread. `dynamic.remaining_energy` and both `is_truncated` keys are new, and the static, dynamic and cell offsets were fixed. `single_voltage` now decodes the variant with a 2-byte header (30-byte M400, 16-byte M4TD and 28-byte M300/M350 records), which used to give a cell count of 0 or a garbage cell.

| Field | Type | Description |
|---|---|---|
| `static.index` | int | Pack index: 0 on single-battery aircraft, 1 or 2 on dual-battery aircraft (one static record per flight there) |
| `static.designed_capacity` | int | Designed capacity (mAh) |
| `static.loop_times` | int | Charge cycle count |
| `static.full_voltage` | int | Designed voltage (mV) |
| `static.manufacture_date` | string | Manufacture date (`YYYY-MM-DD`); `null` when invalid. Replaces `static.temperature` |
| `static.serial` | int | 16-bit serial field of the static record; how it relates to the printed battery serial is not verified |
| `static.life` | int | State of health (%); 0 = unknown (always on Mini 5 Pro) |
| `static.battery_type` | int | Pack type code; the codes are not verified |
| `dynamic.index` | int | 0 on single-battery aircraft; on dual-battery aircraft 0 is the aggregate of both packs, and 1 and 2 are the single packs |
| `dynamic.current_voltage` | float | Voltage (V) |
| `dynamic.current_current` | float | Current (A, absolute value) |
| `dynamic.full_capacity` / `dynamic.remained_capacity` | int | Full-charge and remaining capacity (mAh) |
| `dynamic.temperature` | float | Temperature (°C) |
| `dynamic.cell_size` | int | Cells in series (13 on M400, 12 on M300/M350, 6 on M30/M4TD, 2 on Mini 5 Pro/Neo/Neo 2; not reliable on v12) |
| `dynamic.capacity_percent` | int | State of charge (%) |
| `dynamic.battery_state` | int | 64-bit state bitfield; the bits are not decoded |
| `dynamic.remaining_energy` | float | Remaining energy (Wh), the battery's own estimate; `null` on M300, M350, M4TD and Mavic Mini |
| `dynamic.is_truncated` | bool | `true` when the record is shorter than 22 bytes, so it ends before the state of charge (record byte 21) and the missing fields read 0; a record with only one byte after the kind byte even reads as index 0. The frames ignore such a record (see Battery). `false` in every dynamic record of our 74 decrypted logs |
| `single_voltage.index` | int | Pack index (1 in the M300/M350 records) |
| `single_voltage.cell_count` | int | Number of cells |
| `single_voltage.cell_voltages` | array | Cell voltages (V) |
| `single_voltage.is_truncated` | bool | Fewer voltages than `cell_count`: the 6-byte M4TD records that carry only cell 1 |

##### `VisionGroup` (type 17)

The record is now split into its blocks correctly, so `collision_avoidance_enabled` has real values. The four removed flags have no bit supported by the data or the upstream parser. VisionGroup records exist in 44 of our 74 logs.

| Field | Type | Description |
|---|---|---|
| `vert_low_limit_active` | bool | Ground within the range of the downward sensors |
| `avoidance_flags` | int | The raw avoidance status bitfield, which also shows the bits without a confirmed meaning; `null` when the record has no status block |
| `detections` | object | Radar sector blocks keyed by block number 0–5 (a string in JSON), each `{ position, is_sensor_used, obstacle_distance_m, sectors }` with `sectors` `[{ distance_cm, warning_level }]`. These blocks never occur in our logs, so `detections` is always `{}` and the layout is not verified |

##### `FlightControllerCommonOSD` (type 63)

`need_go_home_time` is `null` instead of 65535 when the aircraft has no estimate. `go_home_capacity` then reads 0; the frames show `batteryPercentNeededToGoHome` as `null` there. `need_go_home_time` and `need_land_time` are also `null` in records of other sub-types than 0.

##### `ADSBFlightData` (type 26)

`altitude` is meters (see Nearby Aircraft above), and `message_type` is a status byte from the record header. Each entry of `aircraft` is now a JSON object:

| Field | Type | Description |
|---|---|---|
| `aircraft[].icao_address` | string | ICAO 24-bit address (6 lowercase hex digits) |
| `aircraft[].latitude` / `aircraft[].longitude` | float | Position (degrees) |
| `aircraft[].altitude` | int | Altitude (m); reference in `altitude_type` |
| `aircraft[].heading` | float | Track heading (degrees) |
| `aircraft[].warning_level` | int | AirSense warning level 0–4 (1 tracked, 2 caution, 3 and up take action). New |
| `aircraft[].altitude_type` | int | 0 WGS84 ellipsoid, 1 above mean sea level. New |
| `aircraft[].relative_altitude` | int | Traffic altitude minus aircraft altitude (m). New |
| `aircraft[].vertical_trend` | int | 0 level, 1 rising, 2 falling. New |
| `aircraft[].distance` | int | Horizontal distance from the aircraft (m). New |

##### `Firmware` (type 15)

The old top-level fields (`sender_type`, `sub_sender_type`, `version`) still hold the first entry.

| Field | Type | Description |
|---|---|---|
| `entries[].sender_type` | int | DUML device type of the module |
| `entries[].sender_name` | string | Device type name (`Camera`, `FlightController`, `Gimbal`, `RemoteController`, `Battery`, ...; `UNKNOWN` for other codes) |
| `entries[].sub_sender_type` | int | Module index (see `firmwareVersions` above) |
| `entries[].version` | string | First three version numbers |
| `entries[].full_version` | string | All four version numbers |

##### Records after 253 and 254

`Custom` (type 5), `AppTip`, `AppWarn` and `AppSeriousWarn` changed value with the October 2026 fix wherever they used to follow a skipped record 253 or 254 (see App Messages above), and about 12,000 `Custom` records that used to be dropped as unreadable appear in raw output since then. This is not a 0.3.0 change.

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

`--extended` changes only the JSON frames; the GeoJSON, KML and CSV exports stay the same.

### Python API

```python
from dji_flightlog_parser import DJILog

log = DJILog.from_file("flight.txt")
keychains = log.fetch_keychains("YOUR_DJI_API_KEY")

# Aggregated frames (10 Hz normalized telemetry, default keys only)
frames = log.frames(keychains)

# Raw parsed records
records = log.records(keychains)

# Frames from records you already have; extended=True adds the extended keys.
# Pass the log version: without it the cell count ignores the cell-count field
# of the dynamic battery records and comes only from the cell records or the
# per-product table (4 for products the table does not know)
from dji_flightlog_parser.frame.builder import records_to_frames
frames = records_to_frames(records, log.details, extended=True, version=log.version)
frames[0].extended.rtk        # FrameRTK; frames[0].to_dict() includes the extended keys

# Summary and frames as one dict (the summary is only built here; default frames only)
from dji_flightlog_parser.parser import parse_file
result = parse_file("flight.txt", api_key="YOUR_DJI_API_KEY")

# Flight metadata
print(log.details.aircraft_name)
print(log.details.product_type)
```

`parse_file()` and `DJILog.frames()` have no `extended` option. To get extended frames together with the summary, call `parse_file()` for the summary and `records_to_frames(log.records(keychains), log.details, extended=True, version=log.version)` for the frames.

With `extended=True` every frame has `frame.extended`, a `FrameExtended` with the five sections (`rtk`, `air_link`, `navigation`, `app_hud`, `secondary_gimbal`); the extra keys of the default sections are attributes of those sections in both modes, but `to_dict()` emits them only for extended frames. `Frame.snapshot()` returns an independent copy of a frame (the builder uses it instead of `copy.deepcopy`). `frame.builder` also exposes the per-log choices it makes: `battery_layout(records, version)` returns a `BatteryLayout` (which dynamic, static and cell-voltage records feed `battery`, the cell count, and whether the log has single packs), `is_valid_dynamic()` is the check that drops truncated and implausible dynamic records, `has_fc_common_osd()` tells whether the type-63 estimates exist, and `main_gimbal_stream()` picks the camera gimbal on airframes with two gimbal devices.

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

The JSON output structure is compatible with the Rust parser, extended with additional fields. The example is an abridged result of `parse_file()`, which returns `version`, `details` (all header values), `frames` and `summary`, in that order; `details` and most frame keys are left out here. The CLI and `export_json()` write `version`, `details` (the Rust parser's shorter set of header values) and `frames`, without `summary`.

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
