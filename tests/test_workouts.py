import pytest

from garmin_coach.workouts import (
    build_running_workout,
    parse_duration,
    parse_pace,
)


def test_parse_pace():
    assert parse_pace("4:30") == 270.0
    assert parse_pace("5:05/km") == 305.0
    with pytest.raises(ValueError):
        parse_pace("4.5")
    with pytest.raises(ValueError):
        parse_pace("4:75")


def test_parse_duration():
    assert parse_duration(90) == 90.0
    assert parse_duration("2:00") == 120.0
    assert parse_duration("1:00:00") == 3600.0
    with pytest.raises(ValueError):
        parse_duration("2m")


def test_distance_step_with_pace_target():
    workout = build_running_workout(
        "test", [{"type": "interval", "distance_km": 1.0, "pace": "4:30-4:45"}]
    )
    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["type"] == "ExecutableStepDTO"
    assert step["stepType"]["stepTypeKey"] == "interval"
    assert step["endCondition"]["conditionTypeKey"] == "distance"
    assert step["endConditionValue"] == 1000.0
    assert step["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    # targetValueOne must be the faster bound (higher m/s)
    assert step["targetValueOne"] == pytest.approx(1000 / 270)
    assert step["targetValueTwo"] == pytest.approx(1000 / 285)
    assert step["targetValueOne"] > step["targetValueTwo"]


def test_pace_bounds_order_does_not_matter():
    a = build_running_workout("a", [{"type": "interval", "time": 60, "pace": "4:45-4:30"}])
    b = build_running_workout("b", [{"type": "interval", "time": 60, "pace": "4:30-4:45"}])
    assert (
        a["workoutSegments"][0]["workoutSteps"][0]["targetValueOne"]
        == b["workoutSegments"][0]["workoutSteps"][0]["targetValueOne"]
    )


def test_time_step_and_hr_zone():
    workout = build_running_workout(
        "test", [{"type": "interval", "time": "20:00", "hr_zone": 2}]
    )
    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["endCondition"]["conditionTypeKey"] == "time"
    assert step["endConditionValue"] == 1200.0
    assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert step["zoneNumber"] == 2
    assert step["targetValueOne"] is None


def test_lap_button_step_has_no_target():
    workout = build_running_workout("test", [{"type": "warmup"}])
    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["endCondition"]["conditionTypeKey"] == "lap.button"
    assert step["endConditionValue"] is None
    assert step["targetType"]["workoutTargetTypeKey"] == "no.target"


def test_repeat_group_nesting_and_step_order():
    workout = build_running_workout(
        "5x1k",
        [
            {"type": "warmup", "distance_km": 2},
            {
                "type": "repeat",
                "count": 5,
                "steps": [
                    {"type": "interval", "distance_km": 1, "pace": "4:30-4:45"},
                    {"type": "recovery", "time": "2:00"},
                ],
            },
            {"type": "cooldown", "distance_km": 1.5},
        ],
    )
    steps = workout["workoutSegments"][0]["workoutSteps"]
    repeat = steps[1]
    assert repeat["type"] == "RepeatGroupDTO"
    assert repeat["numberOfIterations"] == 5
    assert repeat["endCondition"]["conditionTypeKey"] == "iterations"
    assert len(repeat["workoutSteps"]) == 2
    # stepOrder is globally sequential across nesting
    orders = [steps[0]["stepOrder"], repeat["stepOrder"]]
    orders += [s["stepOrder"] for s in repeat["workoutSteps"]]
    orders.append(steps[2]["stepOrder"])
    assert orders == [1, 2, 3, 4, 5]
    # estimated distance: 2km + 5 * 1km + 1.5km
    assert workout["estimatedDistanceInMeters"] == 8500.0


def test_validation_errors():
    with pytest.raises(ValueError, match="unknown step type"):
        build_running_workout("x", [{"type": "sprint", "time": 60}])
    with pytest.raises(ValueError, match="multiple durations"):
        build_running_workout("x", [{"type": "interval", "time": 60, "distance_km": 1}])
    with pytest.raises(ValueError, match="multiple targets"):
        build_running_workout(
            "x", [{"type": "interval", "time": 60, "pace": "4:30-4:45", "hr_zone": 2}]
        )
    with pytest.raises(ValueError, match="range"):
        build_running_workout("x", [{"type": "interval", "time": 60, "pace": "4:30"}])
    with pytest.raises(ValueError, match="repeat"):
        build_running_workout("x", [{"type": "repeat", "count": 0, "steps": []}])
    with pytest.raises(ValueError):
        build_running_workout("x", [])
