"""Record type enum for all known DJI flight log record types."""

from enum import IntEnum


class RecordType(IntEnum):
    OSD = 1
    Home = 2
    Gimbal = 3
    RC = 4
    Custom = 5
    Deform = 6
    CenterBattery = 7
    SmartBattery = 8
    AppTip = 9
    AppWarn = 10
    RCGPS = 11
    RCDebug = 12
    Recover = 13
    AppGPS = 14
    Firmware = 15
    OFDMDebug = 16
    VisionGroup = 17
    VisionWarningString = 18
    MCParams = 19
    APPOperation = 20
    AGOSD = 21
    SmartBatteryGroup = 22
    AppSeriousWarn = 24
    Camera = 25
    ADSBFlightData = 26
    ADSBFlightOriginal = 27
    FlyForbidDBuuid = 28
    AppSpecialControlJoyStick = 29
    AppLowFreqCustom = 30
    NavigationModeGrouped = 31
    GSMissionStatus = 32
    VirtualStick = 33
    GSMissionEvent = 34
    WaypointMissionUpload = 35
    WaypointUpload = 36
    WaypointMissionDownload = 38
    WaypointDownload = 39
    ComponentSerial = 40
    AgricultureDisplayField = 41
    AgricultureRadarPush = 43
    AgricultureSpray = 44
    RTKDifference = 45
    AgricultureFarmMissionInfo = 46
    AgricultureFarmTaskTeam = 47
    AgricultureGroundStationPush = 48
    OFDM = 49
    KeyStorageRecover = 50
    FlySafeLimitInfo = 51
    FlySafeUnlockLicense = 52
    FlightHubInfo = 53
    GOBusiness = 54
    Security = 55
    KeyStorage = 56
    HealthGroup = 58
    FCIMUInfo = 59
    RCDisplayField = 62
    FlightControllerCommonOSD = 63

    @classmethod
    def from_value(cls, val: int) -> "RecordType | int":
        try:
            return cls(val)
        except ValueError:
            return val
