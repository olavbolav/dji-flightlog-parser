"""FeaturePoint enum and record type to feature point mapping."""

from __future__ import annotations

from enum import IntEnum


class FeaturePoint(IntEnum):
    BaseFeature = 1
    VisionFeature = 2
    WaypointFeature = 3
    AgricultureFeature = 4
    AirLinkFeature = 5
    AfterSalesFeature = 6
    DJIFlyCustomFeature = 7
    PlaintextFeature = 8
    FlightHubFeature = 9
    GimbalFeature = 10
    RCFeature = 11
    CameraFeature = 12
    BatteryFeature = 13
    FlySafeFeature = 14
    SecurityFeature = 15

    def api_name(self) -> str:
        """Get the DJI API string name for this feature point."""
        return _FEATURE_POINT_NAMES.get(self, f"Unknown_{self.value}")

    @classmethod
    def from_api_name(cls, name: str) -> FeaturePoint:
        for fp, n in _FEATURE_POINT_NAMES.items():
            if n == name:
                return fp
        raise ValueError(f"Unknown feature point name: {name}")


_FEATURE_POINT_NAMES = {
    FeaturePoint.BaseFeature: "FR_Standardization_Feature_Base_1",
    FeaturePoint.VisionFeature: "FR_Standardization_Feature_Vision_2",
    FeaturePoint.WaypointFeature: "FR_Standardization_Feature_Waypoint_3",
    FeaturePoint.AgricultureFeature: "FR_Standardization_Feature_Agriculture_4",
    FeaturePoint.AirLinkFeature: "FR_Standardization_Feature_AirLink_5",
    FeaturePoint.AfterSalesFeature: "FR_Standardization_Feature_AfterSales_6",
    FeaturePoint.DJIFlyCustomFeature: "FR_Standardization_Feature_DJIFlyCustom_7",
    FeaturePoint.PlaintextFeature: "FR_Standardization_Feature_Plaintext_8",
    FeaturePoint.FlightHubFeature: "FR_Standardization_Feature_FlightHub_9",
    FeaturePoint.GimbalFeature: "FR_Standardization_Feature_Gimbal_10",
    FeaturePoint.RCFeature: "FR_Standardization_Feature_RC_11",
    FeaturePoint.CameraFeature: "FR_Standardization_Feature_Camera_12",
    FeaturePoint.BatteryFeature: "FR_Standardization_Feature_Battery_13",
    FeaturePoint.FlySafeFeature: "FR_Standardization_Feature_FlySafe_14",
    FeaturePoint.SecurityFeature: "FR_Standardization_Feature_Security_15",
}


def feature_point_from_record_type(record_type: int, version: int) -> FeaturePoint:
    """Map a record type byte to its FeaturePoint, considering version differences."""
    if version == 13:
        return _V13_MAP.get(record_type, FeaturePoint.PlaintextFeature)
    return _V14_MAP.get(record_type, FeaturePoint.PlaintextFeature)


_V14_MAP: dict[int, FeaturePoint] = {
    1: FeaturePoint.BaseFeature,            # OSD
    2: FeaturePoint.BaseFeature,            # Home
    3: FeaturePoint.GimbalFeature,          # Gimbal
    4: FeaturePoint.RCFeature,              # RC
    5: FeaturePoint.DJIFlyCustomFeature,    # Custom
    6: FeaturePoint.BaseFeature,            # Deform / MCTripodState
    7: FeaturePoint.BatteryFeature,         # CenterBattery
    8: FeaturePoint.BatteryFeature,         # SmartBattery / PushedBattery
    9: FeaturePoint.DJIFlyCustomFeature,    # AppTip / ShowTips
    10: FeaturePoint.DJIFlyCustomFeature,   # AppWarn / ShowWarning
    11: FeaturePoint.RCFeature,             # RCGPS / RCPushGPS
    12: FeaturePoint.AfterSalesFeature,     # RCDebug
    13: FeaturePoint.BaseFeature,           # Recover / RecoverInfo
    14: FeaturePoint.BaseFeature,           # AppGPS / AppLocation
    15: FeaturePoint.BaseFeature,           # Firmware / FirmwareVersion
    16: FeaturePoint.AfterSalesFeature,     # OFDM / OFDMDebug
    17: FeaturePoint.VisionFeature,         # VisionGroup
    18: FeaturePoint.VisionFeature,         # VisionWarningString
    19: FeaturePoint.AfterSalesFeature,     # MCParams
    20: FeaturePoint.DJIFlyCustomFeature,   # APPOperation
    21: FeaturePoint.AgricultureFeature,    # AGOSD
    22: FeaturePoint.BatteryFeature,        # SmartBatteryGroup
    24: FeaturePoint.DJIFlyCustomFeature,   # AppSeriousWarn / ShowSeriousWarning
    25: FeaturePoint.CameraFeature,         # Camera / CameraInfo
    26: FeaturePoint.AfterSalesFeature,     # ADSBFlightData
    27: FeaturePoint.AfterSalesFeature,     # ADSBFlightOriginal
    28: FeaturePoint.FlySafeFeature,        # FlyForbidDBuuid
    29: FeaturePoint.RCFeature,             # AppSpecialControlJoyStick
    30: FeaturePoint.DJIFlyCustomFeature,   # AppLowFreqCustom
    31: FeaturePoint.WaypointFeature,       # NavigationModeGrouped
    32: FeaturePoint.WaypointFeature,       # GSMissionStatus
    33: FeaturePoint.RCFeature,             # VirtualStick / AppVirtualStick
    34: FeaturePoint.WaypointFeature,       # GSMissionEvent
    35: FeaturePoint.WaypointFeature,       # WaypointMissionUpload
    36: FeaturePoint.WaypointFeature,       # WaypointUpload
    38: FeaturePoint.WaypointFeature,       # WaypointMissionDownload
    39: FeaturePoint.WaypointFeature,       # WaypointDownload
    40: FeaturePoint.BaseFeature,           # ComponentSerial
    41: FeaturePoint.AgricultureFeature,    # AgricultureDisplayField
    43: FeaturePoint.AgricultureFeature,    # AgricultureRadarPush
    44: FeaturePoint.AgricultureFeature,    # AgricultureSpray
    45: FeaturePoint.AgricultureFeature,    # RTKDifference
    46: FeaturePoint.AgricultureFeature,    # AgricultureFarmMissionInfo
    47: FeaturePoint.AgricultureFeature,    # AgricultureFarmTaskTeam
    48: FeaturePoint.AgricultureFeature,    # AgricultureGroundStationPush
    49: FeaturePoint.AirLinkFeature,        # AgricultureOFDMRadioSignalPush
    50: FeaturePoint.PlaintextFeature,      # FlightRecordRecover / KeyStorageRecover
    51: FeaturePoint.FlySafeFeature,        # FlySafeLimitInfo
    52: FeaturePoint.FlySafeFeature,        # FlySafeUnlockLicenseUserActionInfo
    53: FeaturePoint.FlightHubFeature,      # FlightHubInfo
    54: FeaturePoint.DJIFlyCustomFeature,   # GOBusiness
    55: FeaturePoint.SecurityFeature,       # Unknown/Security
    56: FeaturePoint.PlaintextFeature,      # KeyStorage
    58: FeaturePoint.BaseFeature,           # HealthGroup
    59: FeaturePoint.BaseFeature,           # FCIMUInfo
    62: FeaturePoint.RCFeature,             # RCDisplayField
    63: FeaturePoint.BaseFeature,           # FlightControllerCommonOSD
}

_V13_MAP: dict[int, FeaturePoint] = {
    1: FeaturePoint.BaseFeature,            # OSD
    2: FeaturePoint.BaseFeature,            # Home
    3: FeaturePoint.BaseFeature,            # Gimbal (v13: BaseFeature)
    4: FeaturePoint.BaseFeature,            # RC (v13: BaseFeature)
    5: FeaturePoint.DJIFlyCustomFeature,    # Custom
    6: FeaturePoint.BaseFeature,            # Deform / MCTripodState
    7: FeaturePoint.BaseFeature,            # CenterBattery (v13: BaseFeature)
    8: FeaturePoint.BaseFeature,            # SmartBattery (v13: BaseFeature)
    9: FeaturePoint.DJIFlyCustomFeature,    # AppTip / ShowTips
    10: FeaturePoint.DJIFlyCustomFeature,   # AppWarn / ShowWarning
    11: FeaturePoint.BaseFeature,           # RCGPS (v13: BaseFeature)
    12: FeaturePoint.AfterSalesFeature,     # RCDebug
    13: FeaturePoint.BaseFeature,           # Recover / RecoverInfo
    14: FeaturePoint.BaseFeature,           # AppGPS / AppLocation
    15: FeaturePoint.BaseFeature,           # Firmware / FirmwareVersion
    16: FeaturePoint.AfterSalesFeature,     # OFDM / OFDMDebug
    17: FeaturePoint.VisionFeature,         # VisionGroup
    18: FeaturePoint.VisionFeature,         # VisionWarningString
    19: FeaturePoint.AfterSalesFeature,     # MCParams
    20: FeaturePoint.DJIFlyCustomFeature,   # APPOperation
    21: FeaturePoint.AgricultureFeature,    # AGOSD
    22: FeaturePoint.AfterSalesFeature,     # SmartBatteryGroup (v13: AfterSalesFeature)
    24: FeaturePoint.DJIFlyCustomFeature,   # AppSeriousWarn / ShowSeriousWarning
    25: FeaturePoint.BaseFeature,           # Camera (v13: BaseFeature)
    26: FeaturePoint.AfterSalesFeature,     # ADSBFlightData
    27: FeaturePoint.AfterSalesFeature,     # ADSBFlightOriginal
    28: FeaturePoint.AfterSalesFeature,     # FlyForbidDBuuid (v13: AfterSalesFeature)
    29: FeaturePoint.BaseFeature,           # AppSpecialControlJoyStick (v13: BaseFeature)
    30: FeaturePoint.DJIFlyCustomFeature,   # AppLowFreqCustom
    31: FeaturePoint.WaypointFeature,       # NavigationModeGrouped
    32: FeaturePoint.WaypointFeature,       # GSMissionStatus
    33: FeaturePoint.BaseFeature,           # VirtualStick (v13: BaseFeature)
    34: FeaturePoint.WaypointFeature,       # GSMissionEvent
    35: FeaturePoint.WaypointFeature,       # WaypointMissionUpload
    36: FeaturePoint.WaypointFeature,       # WaypointUpload
    38: FeaturePoint.WaypointFeature,       # WaypointMissionDownload
    39: FeaturePoint.WaypointFeature,       # WaypointDownload
    40: FeaturePoint.BaseFeature,           # ComponentSerial
    41: FeaturePoint.AgricultureFeature,    # AgricultureDisplayField
    43: FeaturePoint.AgricultureFeature,    # AgricultureRadarPush
    44: FeaturePoint.AgricultureFeature,    # AgricultureSpray
    45: FeaturePoint.AgricultureFeature,    # RTKDifference
    46: FeaturePoint.AgricultureFeature,    # AgricultureFarmMissionInfo
    47: FeaturePoint.AgricultureFeature,    # AgricultureFarmTaskTeam
    48: FeaturePoint.AgricultureFeature,    # AgricultureGroundStationPush
    49: FeaturePoint.AirLinkFeature,        # AgricultureOFDMRadioSignalPush
    50: FeaturePoint.PlaintextFeature,      # FlightRecordRecover / KeyStorageRecover
    51: FeaturePoint.AfterSalesFeature,     # FlySafeLimitInfo (v13: AfterSalesFeature)
    52: FeaturePoint.AfterSalesFeature,     # FlySafeUnlockLicenseUserActionInfo (v13: AfterSalesFeature)
    53: FeaturePoint.AfterSalesFeature,     # FlightHubInfo (v13: AfterSalesFeature)
    54: FeaturePoint.DJIFlyCustomFeature,   # GOBusiness
    55: FeaturePoint.SecurityFeature,       # Unknown/Security
    56: FeaturePoint.PlaintextFeature,      # KeyStorage
    58: FeaturePoint.BaseFeature,           # HealthGroup
    59: FeaturePoint.BaseFeature,           # FCIMUInfo
    62: FeaturePoint.BaseFeature,           # RCDisplayField (v13: BaseFeature)
    63: FeaturePoint.BaseFeature,           # FlightControllerCommonOSD
}
