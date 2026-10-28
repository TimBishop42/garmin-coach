# garmin-coach

Adaptive running coach for a Garmin Forerunner 55. A weekly headless Claude
Code run reads your recent Garmin Connect training data, compares it against
your goals (`goals.yaml`) and past prescriptions, then creates and schedules
next week's structured workouts on the Garmin Connect calendar — from where
they sync to the watch via the Connect phone app.

Everything runs locally. Garmin credentials are never stored in this repo:
a one-time login persists a self-refreshing token (~1 year) to
`~/.garminconnect` (0700/0600 permissions).

## Prerequisites

A Garmin Connect account, and the [Claude Code
CLI](https://claude.com/claude-code) installed and signed in.

**Install `uv`** — the tool this project uses to install everything else.
It also fetches the right Python version automatically, so there's nothing
separate to install for that. On a Mac: `brew install uv` (no Homebrew?
see [uv's install guide](https://docs.astral.sh/uv/getting-started/installation/)
for a one-line installer instead). On Windows or Linux, use that same guide.

## 1. First run — talk to your coach

This is the manual, conversational way to use it: you open Claude Code,
it looks at your real Garmin data, and you talk through your goals and
your next workout together — no config files to figure out up front.

Open a terminal **inside this project's directory** (the folder containing
`pyproject.toml`) for steps 1–2 below — both commands need to be run from
there.

1. **Install dependencies** — `uv sync` (also downloads Python 3.11 if you
   don't already have it)
2. **Log in to Garmin once, from this same directory** (handles MFA; saves
   a self-refreshing ~1-year token to `~/.garminconnect`, 0700/0600) —
   `uv run garmin-login`
3. **Open Claude Code in this directory and just talk to it.** Try
   something like:
   > Look at my recent runs and training status, then help me set my
   > goals — I want to train for a sub-90-minute half marathon.

   The first time it needs to use one of its tools, Claude Code will ask
   you to approve the `garmin-coach` MCP server — approve it, and it'll
   carry on and answer using your real Garmin data. It will pull your
   activity history and race predictions, ask follow-up questions, and
   write the answers into `goals.yaml` for you. (Prefer to do it by hand
   instead? `goals.yaml` is plain, commented YAML — open it and edit it
   directly.)
4. **Ask it what to do next** — e.g. "what should my next run be?" — and
   have it create and schedule that workout on your Garmin calendar.
   Check it lands in the Garmin Connect app / on your watch.

That's the whole loop, done by hand, whenever you want it.

## 2. Automate it — a coach that runs itself every week

Once you're happy with how it plans things manually, let it run on a
schedule instead of you asking each time. This runs the same tools, but
follows the fixed weekly script in `coach/COACH.md` with no conversation.

- **Try it once manually first:** `./coach/run-weekly.sh` (check
  `logs/coach-*.log` for what it did and why)
- **Or put it on autopilot** — every Sunday at 18:00, **macOS only**, via
  `launchd`:
  ```sh
  cp launchd/com.timbishop.garmin-coach.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.timbishop.garmin-coach.plist
  ```
  Uninstall: `launchctl bootout gui/$(id -u)/com.timbishop.garmin-coach`

## Layout

- `src/garmin_coach/client.py` — thin Garmin Connect wrapper (garminconnect's
  vendored token auth;
  workout create/schedule via the raw `workout-service` endpoints)
- `src/garmin_coach/workouts.py` — step DSL → Garmin workout JSON (unit tested)
- `src/garmin_coach/mcp_server.py` — FastMCP server, ~10 tools
- `coach/COACH.md` — the coaching prompt (procedure, adaptation rules, guardrails)
- `coach/run-weekly.sh` — headless `claude -p` invocation used by launchd
- `goals.yaml` — your goals/constraints; `data/prescriptions.jsonl` — what the
  coach prescribed each week (gitignored, as are `logs/`)

## Notes

- This uses Garmin Connect's unofficial web API (same endpoints as the
  official app, via `python-garminconnect`, which vendors its own auth
  client). Endpoints occasionally
  change; if a run fails, check `logs/` and look for library updates.
- The coach is idempotent per week: it checks `data/prescriptions.jsonl`
  before planning, so re-runs won't double-schedule.

## Tests

```sh
uv run pytest
```
