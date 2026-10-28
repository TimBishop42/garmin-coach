"""Thin Garmin Connect client: reads training data, writes/schedules workouts.

Auth: resumes the token saved by `garmin-login` (see login.py). Workout
create/schedule/delete go through the raw workout-service endpoints via
the vendored auth client (`Garmin(...).client`, from garminconnect>=0.3),
since those are stable and library coverage of them varies. Note: older
garminconnect versions (<0.3) exposed this as `.garth` wrapping the external
garth package instead — if you pin an older version, revert this attribute
name.
"""

import os
from datetime import date
from typing import Any

from garminconnect import Garmin

TOKENSTORE = os.path.expanduser(os.environ.get("GARMINTOKENS", "~/.garminconnect"))

_client: Garmin | None = None


def get_client() -> Garmin:
    global _client
    if _client is None:
        garmin = Garmin()
        try:
            garmin.login(TOKENSTORE)
        except Exception as err:
            raise RuntimeError(
                f"No valid Garmin session in {TOKENSTORE}. "
                "Run `uv run garmin-login` in the garmin-coach directory once to authenticate."
            ) from err
        _client = garmin
    return _client


def _format_pace(seconds_per_km: float) -> str:
    """270.0 -> '4:30'. Rounds to the nearest second without carrying '4:60'."""
    minutes, seconds = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{seconds:02d}"


def _pace_from_speed(average_speed: float | None) -> str | None:
    if not average_speed:
        return None
    return _format_pace(1000.0 / average_speed)


def _summarize_activity(a: dict) -> dict:
    return {
        "activityId": a.get("activityId"),
        "name": a.get("activityName"),
        "type": (a.get("activityType") or {}).get("typeKey"),
        "startTimeLocal": a.get("startTimeLocal"),
        "distance_km": round((a.get("distance") or 0) / 1000.0, 2),
        "duration_min": round((a.get("duration") or 0) / 60.0, 1),
        "avg_pace_min_per_km": _pace_from_speed(a.get("averageSpeed")),
        "avg_hr": a.get("averageHR"),
        "max_hr": a.get("maxHR"),
        "aerobic_training_effect": a.get("aerobicTrainingEffect"),
        "anaerobic_training_effect": a.get("anaerobicTrainingEffect"),
    }


def _summarize_split(lap: dict) -> dict:
    return {
        "lap": lap.get("lapIndex"),
        "distance_km": round((lap.get("distance") or 0) / 1000.0, 2),
        "duration_sec": round(lap.get("duration") or 0, 1),
        "avg_pace_min_per_km": _pace_from_speed(lap.get("averageSpeed")),
        "avg_hr": lap.get("averageHR"),
        "max_hr": lap.get("maxHR"),
        "avg_cadence": lap.get("averageRunCadence"),
        "elevation_gain_m": lap.get("elevationGain"),
    }


def recent_activities(limit: int = 10, type_filter: str = "running") -> list[dict]:
    activities = get_client().get_activities(0, max(limit * 3, limit))
    if type_filter:
        activities = [
            a for a in activities
            if type_filter in ((a.get("activityType") or {}).get("typeKey") or "")
        ]
    return [_summarize_activity(a) for a in activities[:limit]]


def activity_splits(activity_id: int) -> dict:
    raw = get_client().get_activity_splits(activity_id)
    return {
        "activityId": activity_id,
        "laps": [_summarize_split(lap) for lap in (raw.get("lapDTOs") or [])],
    }


def training_status() -> Any:
    return get_client().get_training_status(date.today().isoformat())


def race_predictions() -> Any:
    return get_client().get_race_predictions()


def upload_workout(payload: dict) -> dict:
    return get_client().client.post(
        "connectapi", "/workout-service/workout", json=payload, api=True
    )


def schedule_workout(workout_id: int, on_date: str) -> dict:
    result = get_client().client.post(
        "connectapi",
        f"/workout-service/schedule/{workout_id}",
        json={"date": on_date},
        api=True,
    )
    return result or {"workoutId": workout_id, "scheduled": on_date}


def list_workouts(limit: int = 20) -> list[dict]:
    workouts = get_client().client.connectapi(
        "/workout-service/workouts", params={"start": 0, "limit": limit}
    ) or []
    return [
        {
            "workoutId": w.get("workoutId"),
            "workoutName": w.get("workoutName"),
            "updatedDate": w.get("updateDate") or w.get("updatedDate"),
        }
        for w in workouts
    ]


def delete_workout(workout_id: int) -> dict:
    get_client().client.delete(
        "connectapi", f"/workout-service/workout/{workout_id}", api=True
    )
    return {"workoutId": workout_id, "deleted": True}
