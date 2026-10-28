from unittest.mock import MagicMock, patch

from garmin_coach.client import (
    _format_pace,
    _pace_from_speed,
    _summarize_activity,
    _summarize_split,
    activity_splits,
)


def test_format_pace_basic():
    assert _format_pace(270.0) == "4:30"
    assert _format_pace(305.0) == "5:05"


def test_format_pace_does_not_carry_60_seconds():
    # 299.6s/km rounds to 300s -> must render as 5:00, not the previous 4:60 bug
    assert _format_pace(299.6) == "5:00"


def test_pace_from_speed():
    assert _pace_from_speed(None) is None
    assert _pace_from_speed(0) is None
    assert _pace_from_speed(1000 / 270) == "4:30"


def test_summarize_activity():
    raw = {
        "activityId": 123,
        "activityName": "New York Running",
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-08-17 06:10:38",
        "distance": 14090.0,
        "duration": 4092.0,
        "averageSpeed": 3.4514,
        "averageHR": 147.0,
        "maxHR": 164.0,
    }
    summary = _summarize_activity(raw)
    assert summary["activityId"] == 123
    assert summary["distance_km"] == 14.09
    assert summary["duration_min"] == 68.2
    assert summary["avg_pace_min_per_km"] == "4:50"
    assert summary["avg_hr"] == 147.0


def test_summarize_split():
    raw_lap = {
        "lapIndex": 1,
        "distance": 1000.0,
        "duration": 316.879,
        "averageSpeed": 3.156,
        "averageHR": 139.0,
        "maxHR": 155.0,
        "averageRunCadence": 166.265625,
        "elevationGain": 45.65,
    }
    summary = _summarize_split(raw_lap)
    assert summary == {
        "lap": 1,
        "distance_km": 1.0,
        "duration_sec": 316.9,
        "avg_pace_min_per_km": "5:17",
        "avg_hr": 139.0,
        "max_hr": 155.0,
        "avg_cadence": 166.265625,
        "elevation_gain_m": 45.65,
    }


def test_activity_splits_summarizes_all_laps():
    fake_garmin = MagicMock()
    fake_garmin.get_activity_splits.return_value = {
        "lapDTOs": [
            {"lapIndex": 1, "distance": 1000.0, "duration": 300.0, "averageSpeed": 3.33},
            {"lapIndex": 2, "distance": 1000.0, "duration": 305.0, "averageSpeed": 3.28},
        ]
    }
    with patch("garmin_coach.client.get_client", return_value=fake_garmin):
        result = activity_splits(456)
    assert result["activityId"] == 456
    assert len(result["laps"]) == 2
    assert result["laps"][0]["lap"] == 1
    assert result["laps"][1]["lap"] == 2


def test_activity_splits_handles_missing_lap_dtos():
    fake_garmin = MagicMock()
    fake_garmin.get_activity_splits.return_value = {}
    with patch("garmin_coach.client.get_client", return_value=fake_garmin):
        result = activity_splits(789)
    assert result == {"activityId": 789, "laps": []}
