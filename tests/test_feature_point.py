"""Unit tests for FeaturePoint enum and record type mapping."""

from dji_flightlog_parser.decoder.feature_point import (
    FeaturePoint, feature_point_from_record_type,
)


def test_feature_point_values():
    """Verify enum values match the DJI API numbering."""
    assert FeaturePoint.BaseFeature == 1
    assert FeaturePoint.VisionFeature == 2
    assert FeaturePoint.AirLinkFeature == 5
    assert FeaturePoint.DJIFlyCustomFeature == 7
    assert FeaturePoint.PlaintextFeature == 8
    assert FeaturePoint.GimbalFeature == 10
    assert FeaturePoint.RCFeature == 11
    assert FeaturePoint.CameraFeature == 12
    assert FeaturePoint.BatteryFeature == 13
    assert FeaturePoint.FlySafeFeature == 14
    assert FeaturePoint.SecurityFeature == 15


def test_feature_point_api_names():
    assert FeaturePoint.BaseFeature.api_name() == "FR_Standardization_Feature_Base_1"
    assert FeaturePoint.RCFeature.api_name() == "FR_Standardization_Feature_RC_11"
    assert FeaturePoint.BatteryFeature.api_name() == "FR_Standardization_Feature_Battery_13"


def test_record_type_mapping_v14():
    assert feature_point_from_record_type(1, 14) == FeaturePoint.BaseFeature
    assert feature_point_from_record_type(3, 14) == FeaturePoint.GimbalFeature
    assert feature_point_from_record_type(4, 14) == FeaturePoint.RCFeature
    assert feature_point_from_record_type(7, 14) == FeaturePoint.BatteryFeature
    assert feature_point_from_record_type(25, 14) == FeaturePoint.CameraFeature
    assert feature_point_from_record_type(56, 14) == FeaturePoint.PlaintextFeature


def test_record_type_mapping_v13():
    """v13 maps more types to BaseFeature."""
    assert feature_point_from_record_type(3, 13) == FeaturePoint.BaseFeature
    assert feature_point_from_record_type(4, 13) == FeaturePoint.BaseFeature
    assert feature_point_from_record_type(7, 13) == FeaturePoint.BaseFeature
    assert feature_point_from_record_type(25, 13) == FeaturePoint.BaseFeature


def test_from_api_name():
    fp = FeaturePoint.from_api_name("FR_Standardization_Feature_Camera_12")
    assert fp == FeaturePoint.CameraFeature
