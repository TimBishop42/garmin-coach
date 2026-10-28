"""MCP server exposing the minimal tool surface the running coach needs.

Runs over stdio. Registered in .mcp.json so both interactive Claude Code
sessions and the headless weekly coach run can use it.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastmcp import FastMCP

from . import client
from .workouts import build_running_workout

PROJECT_ROOT = Path(
    os.environ.get("GARMIN_COACH_HOME", Path(__file__).resolve().parents[2])
)
GOALS_PATH = PROJECT_ROOT / "goals.yaml"
LOG_PATH = PROJECT_ROOT / "data" / "prescriptions.jsonl"

mcp = FastMCP(
    "garmin-coach",
    instructions=(
        "Tools for an adaptive running coach backed by Garmin Connect. "
        "Read recent training data, then create and schedule structured "
        "running workouts that sync to the athlete's watch."
    ),
)


@mcp.tool
def get_goals() -> dict:
    """The athlete's pre-configured goals and constraints (goals.yaml)."""
    if not GOALS_PATH.exists():
        raise FileNotFoundError(f"goals.yaml not found at {GOALS_PATH}")
    return yaml.safe_load(GOALS_PATH.read_text())


@mcp.tool
def get_recent_activities(limit: int = 10) -> list[dict]:
    """Recent running activities, newest first: distance, duration, avg pace,
    avg/max HR, and aerobic/anaerobic training effect per session."""
    return client.recent_activities(limit=limit)


@mcp.tool
def get_activity_splits(activity_id: int) -> dict:
    """Per-lap splits for one activity — use on quality sessions to see
    whether interval targets were actually hit. Returns
    {"activityId": ..., "laps": [{"lap", "distance_km", "duration_sec",
    "avg_pace_min_per_km", "avg_hr", "max_hr", "avg_cadence",
    "elevation_gain_m"}, ...]}, one entry per recorded lap (auto laps or
    watch lap-button presses — not necessarily one lap per workout step)."""
    return client.activity_splits(activity_id)


@mcp.tool
def get_training_status() -> dict | list:
    """Garmin's current training status: VO2max, load, load focus."""
    return client.training_status()


@mcp.tool
def get_race_predictions() -> dict | list:
    """Garmin's current race time predictions (5K/10K/half/marathon)."""
    return client.race_predictions()


@mcp.tool
def create_running_workout(name: str, steps_json: str) -> dict:
    """Create a structured running workout in Garmin Connect.

    steps_json is a JSON array of step objects:
      type: warmup | cooldown | interval | recovery | rest | repeat
      duration (exactly one): distance_km (number), distance_m (number),
        time ("MM:SS", "H:MM:SS", or seconds). Omit for lap-button press.
      target (at most one): pace ("4:30-4:45", min/km range),
        hr_zone (1-5), hr ("140-155" bpm range)
      description: optional free text shown on the watch
      repeat steps: {"type": "repeat", "count": N, "steps": [...nested...]}

    Example — 5x1km at threshold with 2min jog recoveries:
      [{"type": "warmup", "distance_km": 2},
       {"type": "repeat", "count": 5, "steps": [
          {"type": "interval", "distance_km": 1, "pace": "4:30-4:45"},
          {"type": "recovery", "time": "2:00"}]},
       {"type": "cooldown", "distance_km": 1.5}]

    Returns the created workoutId — pass it to schedule_workout.
    """
    steps = json.loads(steps_json)
    payload = build_running_workout(name, steps)
    result = client.upload_workout(payload)
    return {"workoutId": result.get("workoutId"), "workoutName": name}


@mcp.tool
def schedule_workout(workout_id: int, date: str) -> dict:
    """Schedule an existing workout on the Garmin Connect calendar
    (date: YYYY-MM-DD). It syncs to the watch via the Connect phone app."""
    return client.schedule_workout(workout_id, date)


@mcp.tool
def list_workouts(limit: int = 20) -> list[dict]:
    """List workouts stored in Garmin Connect (id, name, last update)."""
    return client.list_workouts(limit=limit)


@mcp.tool
def delete_workout(workout_id: int) -> dict:
    """Delete a workout from Garmin Connect (e.g. superseded prescriptions)."""
    return client.delete_workout(workout_id)


@mcp.tool
def log_prescription(week_of: str, rationale: str, workouts_json: str) -> dict:
    """Record what was prescribed and why, so future runs can compare
    prescribed vs actual. week_of: Monday of the planned week (YYYY-MM-DD).
    workouts_json: JSON array of {date, workoutId, name, summary}."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "week_of": week_of,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "rationale": rationale,
        "workouts": json.loads(workouts_json),
    }
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"logged": week_of, "workouts": len(entry["workouts"])}


@mcp.tool
def get_training_log(limit: int = 8) -> list[dict]:
    """Past prescriptions (newest first) — check this before planning to see
    what was assigned in previous weeks and avoid re-planning a week."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text().strip().splitlines()
    return [json.loads(line) for line in reversed(lines[-limit:])]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
