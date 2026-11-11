"""Unit tests for the Camera (25) and Firmware (15) records and the payload summary fields."""

import struct

from dji_flightlog_parser.frame.builder import records_to_frames
from dji_flightlog_parser.parser import _enrich_summary
from dji_flightlog_parser.record.camera import Camera, PhotoState, SDCardState
from dji_flightlog_parser.record.firmware import DeviceType, Firmware
from dji_flightlog_parser.record.osd import OSD
from dji_flightlog_parser.record.reader import Record
from dji_flightlog_parser.record.types import RecordType


def _camera(b0=0x07, b1=0x02, b2=0x80, mode=0, total=60382, free=46096,
            photos=1234, video_s=3600, record_time=0, camera_type=83, n=26) -> bytes:
    data = bytes([b0, b1, b2, 0x00, mode]) + struct.pack(
        "<IIIIH", total, free, photos, video_s, record_time) + bytes([camera_type, 0x01, 0x01])
    assert len(data) == 26
    return data[:n]


def _fw_entry(dev, idx, v) -> bytes:
    return bytes([dev, idx, *v])


# Synthetic entry list in the Matrice 350 layout (payload on gimbal port 2).
# Major version 99 marks the versions as made up.
_FW_M350 = (
    _fw_entry(1, 1, (99, 1, 2, 3)) + _fw_entry(3, 0, (99, 4, 5, 6)) + _fw_entry(4, 1, (99, 7, 8, 9))
    + _fw_entry(6, 0, (99, 10, 11, 12)) + _fw_entry(11, 0, (99, 13, 14, 15))
    + _fw_entry(11, 1, (99, 13, 14, 15))
)


# --- Camera -----------------------------------------------------------------

def test_camera_full_record():
    # connected + USB + time synced, record state 2; SD inserted/normal; storing
    c = Camera.from_bytes(_camera(b0=0x87, b2=0x88, mode=1, record_time=42))
    assert c.is_connected and c.is_usb_connected and c.is_time_synced
    assert c.record_state == 2 and c.is_recording
    assert c.photo_state == PhotoState.NONE and not c.is_shooting_photo
    assert not c.is_shooting_single_photo
    assert c.has_sd_card and c.sd_card_state == SDCardState.Normal
    assert c.is_storing
    assert c.work_mode == 1
    assert (c.sd_card_total_mb, c.sd_card_free_mb) == (60382, 46096)
    assert (c.remaining_photos, c.remaining_video_seconds, c.record_time) == (1234, 3600, 42)
    assert c.camera_type == 83 and c.camera_model == "Zenmuse H30T"


def test_camera_status_bits_are_not_recording_flags():
    # M30/M300/M350/M400 set 0x07 (connected, USB, time sync); M4TD and consumer
    # aircraft set 0x05 (USB clear). These bits used to be read as "taking photo"
    # and "recording".
    c = Camera.from_bytes(_camera(b0=0x07))
    assert not c.is_recording
    assert not c.is_shooting_photo
    assert not c.is_storing  # byte 0 bit 0x08 is part of the photo state, not "storing"


def test_camera_connected_without_usb():
    # Matrice 4TD, Mini 5 Pro, Neo and Neo 2 write 0x05: connected + time synced, no USB
    c = Camera.from_bytes(_camera(b0=0x05, camera_type=99))
    assert c.is_connected and c.is_time_synced and not c.is_usb_connected
    assert not c.is_recording and not c.is_shooting_photo
    assert c.camera_model == "Matrice 4TD Camera"


def test_camera_photo_and_record_states():
    single = Camera.from_bytes(_camera(b0=0x07 | (1 << 3)))
    assert single.photo_state == PhotoState.Single
    assert single.is_shooting_single_photo and single.is_shooting_photo

    pano = Camera.from_bytes(_camera(b0=0x07 | (4 << 3)))
    assert pano.photo_state == PhotoState.FullView
    assert pano.is_shooting_photo and not pano.is_shooting_single_photo

    assert Camera.from_bytes(_camera(b0=0x07 | (5 << 3))).photo_state == PhotoState.UNKNOWN

    # 1 and 3 appear for one record at the start and end of a recording
    for state in (1, 3):
        c = Camera.from_bytes(_camera(b0=0x07 | (state << 6)))
        assert c.record_state == state and c.is_recording


def test_camera_sd_card_bits():
    no_card = Camera.from_bytes(_camera(b1=0x04, total=0, free=0))
    assert not no_card.has_sd_card and no_card.sd_card_state == SDCardState.NotInserted

    to_format = Camera.from_bytes(_camera(b1=0x36))
    assert to_format.has_sd_card and to_format.sd_card_state == SDCardState.SuggestFormat

    slow = Camera.from_bytes(_camera(b1=0x26))
    assert slow.has_sd_card and slow.sd_card_state == SDCardState.Slow


def test_camera_short_and_unknown_type():
    short = Camera.from_bytes(_camera(n=5))
    assert short.work_mode == 0 and short.camera_type is None and short.camera_model is None
    assert short.record_time is None

    unknown = Camera.from_bytes(_camera(camera_type=200))
    assert unknown.camera_type == 200 and unknown.camera_model is None

    assert Camera.from_bytes(b"").camera_type is None


def test_camera_v12_length():
    # Mavic Mini (v12) writes 27 bytes; the extra byte is ignored
    c = Camera.from_bytes(_camera(b0=0x04, b1=0x04, camera_type=44) + b"\x00", version=12)
    assert c.camera_model == "Mavic Mini Camera"
    assert not c.is_connected and not c.is_usb_connected and c.is_time_synced
    assert not c.has_sd_card


# --- Firmware ---------------------------------------------------------------

def test_firmware_entry_list():
    f = Firmware.from_bytes(_FW_M350)
    assert len(f.entries) == 6
    assert (f.sender_type, f.sub_sender_type, f.version) == (1, 1, "99.1.2")  # first entry, legacy fields
    cam = f.entries[0]
    assert (cam.sender_name, cam.sub_sender_type, cam.full_version) == ("Camera", 1, "99.1.2.3")
    assert [e.sender_name for e in f.entries] == [
        "Camera", "FlightController", "Gimbal", "RemoteController", "Battery", "Battery"]
    assert f.entries[5].sub_sender_type == 1


def test_firmware_trailing_byte_and_short():
    f = Firmware.from_bytes(_FW_M350[:30] + b"\x00", version=12)
    assert len(f.entries) == 5

    empty = Firmware.from_bytes(b"\x01\x00\x63\x01\x02")
    assert empty.entries == [] and empty.version == ""

    assert DeviceType(200) == DeviceType.UNKNOWN


# --- summary and frames -----------------------------------------------------

class _Log:
    def __init__(self, records):
        self._last_records = records


def test_summary_payload_fields():
    records = [
        Record(RecordType.Firmware, Firmware.from_bytes(_FW_M350[:18])),
        Record(RecordType.Camera, Camera.from_bytes(_camera(camera_type=83))),
        Record(RecordType.Firmware, Firmware.from_bytes(_FW_M350)),  # repeats the first three
        Record(RecordType.Camera, Camera.from_bytes(_camera(camera_type=61))),
    ]
    summary = {}
    _enrich_summary(_Log(records), [], summary)
    fw = summary["firmwareVersions"]
    assert len(fw) == 6
    assert fw[0] == {"senderType": 1, "subSenderType": 1, "version": "99.1.2",
                     "senderName": "Camera", "fullVersion": "99.1.2.3"}
    assert [(e["senderName"], e["subSenderType"]) for e in fw][-2:] == [("Battery", 0), ("Battery", 1)]
    # First camera record wins
    assert summary["cameraType"] == 83 and summary["cameraModel"] == "Zenmuse H30T"


def test_summary_firmware_keeps_each_full_version():
    # Same module, only the 4th version byte differs: both builds are listed
    changed = _FW_M350[:5] + bytes([_FW_M350[5] + 1])
    records = [Record(RecordType.Firmware, Firmware.from_bytes(_FW_M350)),
               Record(RecordType.Firmware, Firmware.from_bytes(changed))]
    summary = {}
    _enrich_summary(_Log(records), [], summary)
    cams = [e["fullVersion"] for e in summary["firmwareVersions"] if e["senderName"] == "Camera"]
    assert cams == ["99.1.2.3", "99.1.2.4"]


def test_summary_payload_fields_skipped_for_undecrypted_log():
    # v13+ parsed without keys: these records are encrypted noise
    log = _Log([Record(RecordType.Firmware, Firmware.from_bytes(_FW_M350)),
                Record(RecordType.Camera, Camera.from_bytes(_camera(camera_type=83)))])
    log._undecrypted = True
    summary = {}
    _enrich_summary(log, [], summary)
    assert summary == {}


def test_summary_without_camera_or_firmware():
    summary = {}
    _enrich_summary(_Log([Record(RecordType.Camera, Camera.from_bytes(_camera(n=5)))]), [], summary)
    assert "cameraType" not in summary and "firmwareVersions" not in summary


def test_frame_camera_fields():
    osd = OSD.from_bytes(bytes(60))
    records = [
        Record(RecordType.OSD, osd),
        Record(RecordType.OSD, osd),
        Record(RecordType.Camera, Camera.from_bytes(_camera(b0=0x87, mode=1, record_time=5))),
        Record(RecordType.OSD, osd),
        Record(RecordType.Camera, Camera.from_bytes(_camera(b0=0x07 | (1 << 3), b1=0x04))),
        Record(RecordType.OSD, osd),
    ]
    frames = [f.to_dict()["camera"] for f in records_to_frames(records)]
    assert frames[1] == {"isPhoto": False, "isVideo": True,
                         "sdCardIsInserted": True, "sdCardState": "Normal"}
    assert frames[2] == {"isPhoto": True, "isVideo": False,
                         "sdCardIsInserted": False, "sdCardState": "NotInserted"}


def test_frame_is_photo_for_all_photo_states():
    osd = OSD.from_bytes(bytes(60))
    records = [Record(RecordType.OSD, osd), Record(RecordType.OSD, osd)]
    for state in (PhotoState.Multiple, PhotoState.HDR, PhotoState.FullView):
        records += [
            Record(RecordType.Camera, Camera.from_bytes(_camera(b0=0x07 | (state << 3)))),
            Record(RecordType.OSD, osd),
        ]
    frames = [f.to_dict()["camera"] for f in records_to_frames(records)]
    assert [f["isPhoto"] for f in frames[1:4]] == [True, True, True]


def test_frame_is_photo_resets_but_video_carries():
    osd = OSD.from_bytes(bytes(60))
    records = [
        Record(RecordType.OSD, osd),
        Record(RecordType.OSD, osd),
        # Photo then idle within the same frame: the frame keeps isPhoto
        Record(RecordType.Camera, Camera.from_bytes(_camera(b0=0x87 | (1 << 3)))),
        Record(RecordType.Camera, Camera.from_bytes(_camera(b0=0x87))),
        Record(RecordType.OSD, osd),
        Record(RecordType.OSD, osd),
    ]
    frames = [f.to_dict()["camera"] for f in records_to_frames(records)]
    assert frames[1]["isPhoto"] and frames[1]["isVideo"]
    assert not frames[2]["isPhoto"] and frames[2]["isVideo"]


# --- second gimbal (Matrice 4TD top accessory) ---------------------------------

from dji_flightlog_parser.frame.builder import main_gimbal_stream  # noqa: E402
from dji_flightlog_parser.record.gimbal import Gimbal  # noqa: E402


def _gimbal(stream, pitch=-30.0, roll=0.0, yaw=10.0, limits=0) -> Gimbal:
    data = struct.pack("<hhh", round(pitch * 10), round(roll * 10), round(yaw * 10))
    data += bytes([0x80, 0x00, 0x00, 0x00, limits, stream])
    return Gimbal.from_bytes(data, version=14)


def _grec(*args, **kw) -> Record:
    return Record(RecordType.Gimbal, _gimbal(*args, **kw))


def test_main_gimbal_stream_single_device():
    assert main_gimbal_stream([_grec(1, roll=5.0), _grec(1, roll=-5.0)]) is None
    assert main_gimbal_stream([Record(RecordType.OSD, OSD.from_bytes(bytes(60)))]) is None


def test_main_gimbal_stream_picks_roll_stabilised_device():
    # Accessory (stream 1) rolls with the aircraft; camera (stream 2) stays level
    records = []
    for i in range(20):
        records += [_grec(1, roll=(-6.0 if i % 2 else 6.0)), _grec(2, roll=0.1)]
    assert main_gimbal_stream(records) == 2
    # The id itself does not matter
    swapped = [_grec(3 - r.data.version, roll=r.data.roll) for r in records]
    assert main_gimbal_stream(swapped) == 1


def test_main_gimbal_stream_ignores_rare_stream_and_breaks_ties():
    # A level stream with under 10% of the records is not a candidate
    records = [_grec(1, roll=4.0) for _ in range(20)] + [_grec(2, roll=0.0)]
    assert main_gimbal_stream(records) == 1
    # Equal roll: the higher stream id wins
    assert main_gimbal_stream([_grec(1), _grec(2)]) == 2


def test_frames_follow_camera_gimbal_and_extended_shows_accessory():
    osd = Record(RecordType.OSD, OSD.from_bytes(bytes(60)))
    records = [osd]
    for i in range(4):
        records += [
            # Camera tilts to +60 and sits at its pitch limit; accessory stops at +35
            _grec(2, pitch=60.0, roll=0.0, limits=0x01),
            _grec(1, pitch=32.0 + i, roll=(-5.0 if i % 2 else 5.0), yaw=-20.0 - i,
                  limits=(0x01 if i == 2 else 0)),
            osd,
        ]
    plain = [f.to_dict() for f in records_to_frames(records)]
    assert "secondaryGimbal" not in plain[1]
    assert all(f["gimbal"]["pitch"] == 60.0 and f["gimbal"]["roll"] == 0.0 for f in plain)
    assert all(f["gimbal"]["isPitchAtLimit"] for f in plain)
    # One endpoint tip when the limit is first reached, not one per accessory record
    assert sum(f["app"]["tip"].count("Gimbal pitch axis endpoint reached.") for f in plain) == 1

    ext = [f.to_dict() for f in records_to_frames(records, extended=True)]
    assert [tuple(f["secondaryGimbal"].values()) for f in ext] == [
        (32.0, 5.0, -20.0, False),
        (33.0, -5.0, -21.0, False),
        (34.0, 5.0, -22.0, True),
        (35.0, -5.0, -23.0, False),
        (35.0, -5.0, -23.0, False),  # carried into the last frame
    ]
    # Extended frames add keys to gimbal but keep the default ones unchanged
    assert {k: ext[-1]["gimbal"][k] for k in plain[-1]["gimbal"]} == plain[-1]["gimbal"]


def test_single_gimbal_logs_keep_secondary_null():
    osd = Record(RecordType.OSD, OSD.from_bytes(bytes(60)))
    records = [osd, _grec(1, pitch=-45.0, roll=3.0), osd, _grec(1, pitch=-40.0, roll=-3.0), osd]
    ext = [f.to_dict() for f in records_to_frames(records, extended=True)]
    assert [f["gimbal"]["pitch"] for f in ext] == [-45.0, -40.0, -40.0]
    assert all(f["secondaryGimbal"] == {"pitch": None, "roll": None, "yaw": None, "isPitchAtLimit": None}
               for f in ext)


def test_main_gimbal_stream_candidate_threshold_boundaries():
    # Exactly 10% of the records: still a candidate
    records = [_grec(1, roll=4.0) for _ in range(9)] + [_grec(2, roll=0.0)]
    assert main_gimbal_stream(records) == 2
    # Just under 10% (1 of 11): not a candidate
    records = [_grec(1, roll=4.0) for _ in range(10)] + [_grec(2, roll=0.0)]
    assert main_gimbal_stream(records) == 1
    # Real dual logs are not exactly 50/50 (one has 49.93% camera records)
    records = [_grec(1, roll=4.0) for _ in range(51)] + [_grec(2, roll=0.0) for _ in range(49)]
    assert main_gimbal_stream(records) == 2


def test_records_to_frames_accepts_iterators():
    osd = Record(RecordType.OSD, OSD.from_bytes(bytes(60)))
    records = [osd, _grec(2, roll=0.0), _grec(1, roll=5.0), osd, osd]
    assert len(records_to_frames(iter(records))) == len(records_to_frames(records)) == 3
