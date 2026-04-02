"""OSD (On-Screen Display / aircraft state) record parser."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import IntEnum


class FlightMode(IntEnum):
    Manual = 0
    Atti = 1
    AttiCourseLock = 2
    AttiHover = 3
    Hover = 4
    GPSBlake = 5
    GPSAtti = 6
    GPSCourseLock = 7
    GPSHomeLock = 8
    GPSHotPoint = 9
    AssistedTakeoff = 10
    AutoTakeoff = 11
    AutoLanding = 12
    AttiLanding = 13
    GPSWaypoint = 14
    GoHome = 15
    ClickGo = 16
    Joystick = 17
    GPSAttiWristband = 18
    Cinematic = 19
    AttiLimited = 23
    Draw = 24
    GPSFollowMe = 25
    ActiveTrack = 26
    TapFly = 27
    Pano = 28
    Farming = 29
    FPV = 30
    GPSSport = 31
    GPSNovice = 32
    ConfirmLanding = 33
    TerrainTracking = 35
    NaviAdvGoHome = 36
    NaviAdvLanding = 37
    Tripod = 38
    TrackHeadlock = 39
    EngineStart = 41
    GPSGentle = 43

    @classmethod
    def _missing_(cls, value: object) -> FlightMode:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class AppCommand(IntEnum):
    AutoFly = 1
    AutoLanding = 2
    HomePointNow = 3
    HomePointHot = 4
    HomePointLock = 5
    GoHome = 6
    StartMotor = 7
    StopMotor = 8
    Calibration = 9
    DeformProtecClose = 10
    DeformProtecOpen = 11
    DropGoHome = 12
    DropTakeOff = 13
    DropLanding = 14
    DynamicHomePointOpen = 15
    DynamicHomePointClose = 16
    FollowFunctionOpen = 17
    FollowFunctionClose = 18
    IOCOpen = 19
    IOCClose = 20
    DropCalibration = 21
    PackMode = 22
    UnPackMode = 23
    EnterManualMode = 24
    StopDeform = 25
    DownDeform = 28
    UpDeform = 29
    ForceLanding = 30
    ForceLanding2 = 31

    @classmethod
    def _missing_(cls, value: object) -> AppCommand:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class GroundOrSky(IntEnum):
    Ground = 0
    Sky = 2

    @classmethod
    def _missing_(cls, value: object) -> GroundOrSky:
        if value in (0, 1):
            return cls.Ground
        if value in (2, 3):
            return cls.Sky
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class GoHomeStatus(IntEnum):
    Standby = 0
    Preascending = 1
    Align = 2
    Ascending = 3
    Cruise = 4
    Braking = 5
    Bypassing = 6

    @classmethod
    def _missing_(cls, value: object) -> GoHomeStatus:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class FlightAction(IntEnum):
    NONE = 0
    WarningPowerGoHome = 1
    WarningPowerLanding = 2
    SmartPowerGoHome = 3
    SmartPowerLanding = 4
    LowVoltageLanding = 5
    LowVoltageGoHome = 6
    SeriousLowVoltageLanding = 7
    RCOnekeyGoHome = 8
    RCAssistantTakeoff = 9
    RCAutoTakeoff = 10
    RCAutoLanding = 11
    AppAutoGoHome = 12
    AppAutoLanding = 13
    AppAutoTakeoff = 14
    OutOfControlGoHome = 15
    ApiAutoTakeoff = 16
    ApiAutoLanding = 17
    ApiAutoGoHome = 18
    AvoidGroundLanding = 19
    AirportAvoidLanding = 20
    TooCloseGoHomeLanding = 21
    TooFarGoHomeLanding = 22
    AppWPMission = 23
    WPAutoTakeoff = 24
    GoHomeAvoid = 25
    PGoHomeFinish = 26
    VertLowLimitLanding = 27
    BatteryForceLanding = 28
    MCProtectGoHome = 29
    MotorblockLanding = 30
    AppRequestForceLanding = 31
    FakeBatteryLanding = 32
    RTHComingObstacleLanding = 33
    IMUErrorRTH = 34

    @classmethod
    def _missing_(cls, value: object) -> FlightAction:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class MotorStartFailedCause(IntEnum):
    NONE = 0
    CompassError = 1
    AssistantProtected = 2
    DeviceLocked = 3
    DistanceLimit = 4
    IMUNeedCalibration = 5
    IMUSNError = 6
    IMUWarning = 7
    CompassCalibrating = 8
    AttiError = 9
    NoviceProtected = 10
    BatteryCellError = 11
    BatteryCommuniteError = 12
    SeriousLowVoltage = 13
    SeriousLowPower = 14
    LowVoltage = 15
    TempureVolLow = 16
    SmartLowToLand = 17
    BatteryNotReady = 18
    SimulatorMode = 19
    PackMode = 20
    AttitudeAbnormal = 21
    UnActive = 22
    FlyForbiddenError = 23
    BiasError = 24
    EscError = 25
    ImuInitError = 26
    SystemUpgrade = 27
    SimulatorStarted = 28
    ImuingError = 29
    AttiAngleOver = 30
    GyroscopeError = 31
    AcceleratorError = 32
    CompassFailed = 33
    BarometerError = 34
    BarometerNegative = 35
    CompassBig = 36
    GyroscopeBiasBig = 37
    AcceleratorBiasBig = 38
    CompassNoiseBig = 39
    BarometerNoiseBig = 40
    InvalidSn = 41
    FlashOperating = 44
    GPSdisconnect = 45
    SDCardException = 47
    IMUNoconnection = 61
    RCCalibration = 62
    RCCalibrationException = 63
    RCCalibrationUnfinished = 64
    AircraftTypeMismatch = 67
    FoundUnfinishedModule = 68
    CyroAbnormal = 70
    BaroAbnormal = 71
    CompassAbnormal = 72
    GPSAbnormal = 73
    NSAbnormal = 74
    TopologyAbnormal = 75
    RCNeedCali = 76
    InvalidFloat = 77

    @classmethod
    def _missing_(cls, value: object) -> MotorStartFailedCause:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class NonGPSCause(IntEnum):
    Already = 0
    Forbid = 1
    GpsNumNonEnough = 2
    GpsHdopLarge = 3
    GpsPositionNonMatch = 4
    SpeedErrorLarge = 5
    YawErrorLarge = 6
    CompassErrorLarge = 7

    @classmethod
    def _missing_(cls, value: object) -> NonGPSCause:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class BatteryType(IntEnum):
    NonSmart = 1
    Smart = 2

    @classmethod
    def _missing_(cls, value: object) -> BatteryType:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


class DroneType(IntEnum):
    NONE = 0
    Inspire1 = 1
    Phantom3Advanced = 2
    Phantom3Pro = 3
    Phantom3Standard = 4
    OpenFrame = 5
    AceOne = 6
    WKM = 7
    Naza = 8
    A2 = 9
    A3 = 10
    Phantom4 = 11
    Matrice600 = 14
    Phantom34K = 15
    MavicPro = 16
    Inspire2 = 17
    Phantom4Pro = 18
    N3 = 20
    Spark = 21
    Matrice600Pro = 23
    MavicAir = 24
    Matrice200 = 25
    Phantom4Advanced = 27
    Matrice210 = 28
    Phantom3SE = 29
    Matrice210RTK = 30
    Phantom4ProV2 = 36
    Mavic2 = 41
    Mavic2Enterprise = 51
    MavicAir2 = 58
    Matrice300RTK = 60
    Mini2 = 63
    Mavic3Enterprise = 77
    Mavic3Pro = 84
    Matrice350RTK = 89
    Mini4Pro = 93
    Avata2 = 94

    @classmethod
    def _missing_(cls, value: object) -> DroneType:
        obj = int.__new__(cls, value)
        obj._name_ = str(value)
        obj._value_ = value
        return obj


class ImuInitFailReason(IntEnum):
    MonitorError = 0
    CollectingData = 1
    AcceDead = 3
    CompassDead = 4
    BarometerDead = 5
    BarometerNegative = 6
    CompassModTooLarge = 7
    GyroBiasTooLarge = 8
    AcceBiasTooLarge = 9
    CompassNoiseTooLarge = 10
    BarometerNoiseTooLarge = 11
    WaitingMcStationary = 12
    AcceMoveTooLarge = 13
    McHeaderMoved = 14
    McVibrated = 15

    @classmethod
    def _missing_(cls, value: object) -> ImuInitFailReason:
        obj = int.__new__(cls, value)
        obj._name_ = f"Unknown({value})"
        obj._value_ = value
        return obj


def _sub_byte(byte_val: int, mask: int) -> int:
    """Extract bits from a byte using a mask, shifting to LSB."""
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class OSD:
    longitude: float = 0.0
    latitude: float = 0.0
    altitude: float = 0.0
    speed_x: float = 0.0
    speed_y: float = 0.0
    speed_z: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    flight_mode: FlightMode = FlightMode.Manual
    rc_outcontrol: bool = False
    app_command: AppCommand | int = 0
    can_ioc_work: bool = False
    ground_or_sky: GroundOrSky = GroundOrSky.Ground
    is_motor_up: bool = False
    is_swave_work: bool = False
    go_home_status: GoHomeStatus = GoHomeStatus.Standby
    is_vision_used: bool = False
    voltage_warning: int = 0
    is_imu_preheated: bool = False
    mode_channel: int = 0
    is_gps_valid: bool = False
    is_compass_error: bool = False
    wave_error: bool = False
    gps_level: int = 0
    battery_type: BatteryType | int = 0
    is_out_of_limit: bool = False
    is_go_home_height_modified: bool = False
    is_propeller_catapult: bool = False
    is_motor_blocked: bool = False
    is_not_enough_force: bool = False
    is_barometer_dead_in_air: bool = False
    is_vibrating: bool = False
    is_acceletor_over_range: bool = False
    gps_num: int = 0
    flight_action: FlightAction = FlightAction.NONE
    motor_start_failed_cause: MotorStartFailedCause = MotorStartFailedCause.NONE
    non_gps_cause: NonGPSCause = NonGPSCause.Already
    waypoint_limit_mode: bool = False
    battery: int = 0
    s_wave_height: float = 0.0
    fly_time: float = 0.0
    motor_revolution: int = 0
    version_c: int = 0
    drone_type: DroneType | int = 0
    imu_init_fail_reason: ImuInitFailReason = ImuInitFailReason.MonitorError

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> OSD:
        o = cls()
        if len(data) < 30:
            return o

        o.longitude = math.degrees(struct.unpack_from("<d", data, 0)[0])
        o.latitude = math.degrees(struct.unpack_from("<d", data, 8)[0])
        o.altitude = struct.unpack_from("<h", data, 16)[0] / 10.0
        o.speed_x = struct.unpack_from("<h", data, 18)[0] / 10.0
        o.speed_y = struct.unpack_from("<h", data, 20)[0] / 10.0
        o.speed_z = struct.unpack_from("<h", data, 22)[0] / 10.0
        o.pitch = struct.unpack_from("<h", data, 24)[0] / 10.0
        o.roll = struct.unpack_from("<h", data, 26)[0] / 10.0
        o.yaw = struct.unpack_from("<h", data, 28)[0] / 10.0

        if len(data) > 30:
            bp1 = data[30]
            o.flight_mode = FlightMode(_sub_byte(bp1, 0x7F))
            o.rc_outcontrol = bool(bp1 & 0x80)

        if len(data) > 31:
            o.app_command = AppCommand(data[31])

        if len(data) > 32:
            bp2 = data[32]
            o.can_ioc_work = bool(bp2 & 0x01)
            o.ground_or_sky = GroundOrSky(_sub_byte(bp2, 0x06))
            o.is_motor_up = bool(bp2 & 0x08)
            o.is_swave_work = bool(bp2 & 0x10)
            o.go_home_status = GoHomeStatus(_sub_byte(bp2, 0xE0))

        if len(data) > 33:
            bp3 = data[33]
            o.is_vision_used = bool(bp3 & 0x01)
            o.voltage_warning = _sub_byte(bp3, 0x06)
            o.is_imu_preheated = bool(bp3 & 0x10)
            o.mode_channel = _sub_byte(bp3, 0x60)
            o.is_gps_valid = bool(bp3 & 0x80)

        if len(data) > 34:
            bp4 = data[34]
            o.is_compass_error = bool(bp4 & 0x01)
            o.wave_error = bool(bp4 & 0x02)
            o.gps_level = _sub_byte(bp4, 0x3C)
            o.battery_type = BatteryType(_sub_byte(bp4, 0xC0))

        if len(data) > 35:
            bp5 = data[35]
            o.is_out_of_limit = bool(bp5 & 0x01)
            o.is_go_home_height_modified = bool(bp5 & 0x02)
            o.is_propeller_catapult = bool(bp5 & 0x04)
            o.is_motor_blocked = bool(bp5 & 0x08)
            o.is_not_enough_force = bool(bp5 & 0x10)
            o.is_barometer_dead_in_air = bool(bp5 & 0x20)
            o.is_vibrating = bool(bp5 & 0x40)
            o.is_acceletor_over_range = bool(bp5 & 0x80)

        if len(data) > 36:
            o.gps_num = data[36]
        if len(data) > 37:
            o.flight_action = FlightAction(data[37])
        if len(data) > 38:
            o.motor_start_failed_cause = MotorStartFailedCause(data[38])

        if len(data) > 39:
            bp6 = data[39]
            o.non_gps_cause = NonGPSCause(_sub_byte(bp6, 0x0F))
            o.waypoint_limit_mode = bool(bp6 & 0x10)

        if len(data) > 40:
            o.battery = data[40]
        if len(data) > 41:
            o.s_wave_height = data[41] / 10.0
        if len(data) > 43:
            o.fly_time = struct.unpack_from("<H", data, 42)[0] / 10.0
        if len(data) > 44:
            o.motor_revolution = data[44]
        if len(data) > 47:
            o.version_c = data[47]

        offset = 48
        if version >= 2 and len(data) > offset:
            o.drone_type = DroneType(data[offset])
            offset += 1
        if version >= 3 and len(data) > offset:
            o.imu_init_fail_reason = ImuInitFailReason(data[offset])

        return o
