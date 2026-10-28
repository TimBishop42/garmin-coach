"""Build Garmin Connect workout-service payloads from a simple step DSL.

The DSL is a list of step dicts, designed to be easy for an LLM (or a human)
to produce:

    [
      {"type": "warmup", "distance_km": 2.0},
      {"type": "repeat", "count": 5, "steps": [
          {"type": "interval", "distance_km": 1.0, "pace": "4:30-4:45"},
          {"type": "recovery", "time": "2:00"},
      ]},
      {"type": "interval", "time": "20:00", "hr_zone": 2},
      {"type": "cooldown", "distance_km": 1.5},
    ]

Step types: warmup | cooldown | interval | recovery | rest | repeat
Duration (exactly one, except repeat): distance_km, distance_m, time
  ("MM:SS", "H:MM:SS", or plain seconds). Omit all three for lap-button.
Targets (at most one): pace ("M:SS-M:SS" min/km range),
  hr_zone (1-5), hr ("140-155" custom bpm range).
Repeat steps take: count (iterations) and steps (nested list).

Garmin encodes pace targets in metres/second; targetValueOne must be the
faster bound (higher m/s), targetValueTwo the slower bound.
"""

from typing import Any, Iterator

SPORT_RUNNING = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}

STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
}

END_LAP_BUTTON = {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True}
END_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
END_DISTANCE = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
END_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}

TARGET_NONE = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
TARGET_HR = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4}
TARGET_PACE = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}


def parse_pace(pace: str) -> float:
    """'4:30' (min/km) -> 270.0 seconds per km."""
    pace = pace.strip().removesuffix("/km").strip()
    parts = pace.split(":")
    if len(parts) != 2:
        raise ValueError(f"pace must look like 'M:SS' min/km, got {pace!r}")
    minutes, seconds = int(parts[0]), int(parts[1])
    if not (0 <= seconds < 60) or minutes <= 0:
        raise ValueError(f"invalid pace {pace!r}")
    return minutes * 60.0 + seconds


def parse_duration(value: Any) -> float:
    """Seconds from a number, 'MM:SS', or 'H:MM:SS'."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = [int(p) for p in str(value).strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60.0 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
    raise ValueError(f"time must be seconds, 'MM:SS' or 'H:MM:SS', got {value!r}")


def _pace_range_to_mps(pace_range: str) -> tuple[float, float]:
    """'4:30-4:45' -> (m/s faster bound, m/s slower bound)."""
    parts = pace_range.split("-")
    if len(parts) != 2:
        raise ValueError(
            f"pace must be a range like '4:30-4:45' (min/km), got {pace_range!r}"
        )
    speeds = sorted(1000.0 / parse_pace(p) for p in parts)
    return speeds[1], speeds[0]


def _end_condition(spec: dict) -> tuple[dict, float | None]:
    duration_keys = [k for k in ("distance_km", "distance_m", "time") if k in spec]
    if len(duration_keys) > 1:
        raise ValueError(f"step has multiple durations {duration_keys}: {spec}")
    if "distance_km" in spec:
        return END_DISTANCE, float(spec["distance_km"]) * 1000.0
    if "distance_m" in spec:
        return END_DISTANCE, float(spec["distance_m"])
    if "time" in spec:
        return END_TIME, parse_duration(spec["time"])
    return END_LAP_BUTTON, None


def _target(spec: dict) -> dict:
    target_keys = [k for k in ("pace", "hr_zone", "hr") if k in spec]
    if len(target_keys) > 1:
        raise ValueError(f"step has multiple targets {target_keys}: {spec}")
    if "pace" in spec:
        faster, slower = _pace_range_to_mps(spec["pace"])
        return {"targetType": TARGET_PACE, "targetValueOne": faster, "targetValueTwo": slower, "zoneNumber": None}
    if "hr_zone" in spec:
        zone = int(spec["hr_zone"])
        if not 1 <= zone <= 5:
            raise ValueError(f"hr_zone must be 1-5, got {zone}")
        return {"targetType": TARGET_HR, "targetValueOne": None, "targetValueTwo": None, "zoneNumber": zone}
    if "hr" in spec:
        parts = str(spec["hr"]).split("-")
        if len(parts) != 2:
            raise ValueError(f"hr must be a bpm range like '140-155', got {spec['hr']!r}")
        low, high = sorted(float(p) for p in parts)
        return {"targetType": TARGET_HR, "targetValueOne": low, "targetValueTwo": high, "zoneNumber": None}
    return {"targetType": TARGET_NONE, "targetValueOne": None, "targetValueTwo": None, "zoneNumber": None}


def _build_step(spec: dict, order: Iterator[int]) -> dict:
    step_type = spec.get("type")
    if step_type not in STEP_TYPES:
        raise ValueError(
            f"unknown step type {step_type!r}; expected one of {sorted(STEP_TYPES)}"
        )

    if step_type == "repeat":
        count = int(spec.get("count", 0))
        children = spec.get("steps") or []
        if count < 1 or not children:
            raise ValueError(f"repeat step needs count >= 1 and non-empty steps: {spec}")
        step_order = next(order)
        return {
            "type": "RepeatGroupDTO",
            "stepId": step_order,
            "stepOrder": step_order,
            "stepType": STEP_TYPES["repeat"],
            "numberOfIterations": count,
            "smartRepeat": False,
            "endCondition": END_ITERATIONS,
            "endConditionValue": float(count),
            "workoutSteps": [_build_step(child, order) for child in children],
        }

    end_condition, end_value = _end_condition(spec)
    target = _target(spec)
    step_order = next(order)
    return {
        "type": "ExecutableStepDTO",
        "stepId": step_order,
        "stepOrder": step_order,
        "stepType": STEP_TYPES[step_type],
        "description": spec.get("description"),
        "stepAudioNote": None,
        "endCondition": end_condition,
        "endConditionValue": end_value,
        "targetType": target["targetType"],
        "targetValueOne": target["targetValueOne"],
        "targetValueTwo": target["targetValueTwo"],
        "zoneNumber": target["zoneNumber"],
        "targetValueUnit": None,
    }


def _estimated_distance_m(steps: list[dict]) -> float:
    total = 0.0
    for spec in steps:
        if spec.get("type") == "repeat":
            total += int(spec.get("count", 0)) * _estimated_distance_m(spec.get("steps") or [])
        elif "distance_km" in spec:
            total += float(spec["distance_km"]) * 1000.0
        elif "distance_m" in spec:
            total += float(spec["distance_m"])
    return total


def build_running_workout(name: str, steps: list[dict]) -> dict:
    """Build the full POST /workout-service/workout payload."""
    if not name or not steps:
        raise ValueError("workout needs a name and at least one step")
    order = iter(range(1, 10_000))
    return {
        "workoutName": name,
        "sportType": SPORT_RUNNING,
        "subSportType": None,
        "estimatedDistanceUnit": {"unitKey": None},
        "avgTrainingSpeed": None,
        "estimateType": None,
        "estimatedDistanceInMeters": _estimated_distance_m(steps),
        "estimatedDurationInSecs": None,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": SPORT_RUNNING,
                "workoutSteps": [_build_step(s, order) for s in steps],
            }
        ],
    }
