"""The stand-in judge and client patch shared by every Mario experiment.

Not a runnable script any more: the synthetic-environment episode drivers it once
contained were removed when the folder was tidied (the real-emulator path made them
redundant; the full story is in REPORT.md).  What remains is the load-bearing part
that the real-emulator scripts import:

* ``ScriptedPilotTransport`` — answers ``system_one`` requests in the SDK wire
  format, choosing via a rule-based pilot that reads only the published state. The
  answers are NOT Jev's; they exist so experiments run without an API key. The
  experiment entry points intentionally install this transport; setting
  ``TYPESAFE_API_KEY`` alone does not switch them to a real Jev call.
* ``patched_client`` — swaps the SDK client class so ``TypeSafePolicy`` constructs a
  client routed through the transport above, optionally merging cross-episode memory
  into the outgoing state.
* ``summarise`` — turn a run's JSONL artifact into metrics.

Run scripts that use it: ``repro_real_env.py``, ``ab_real_env.py``, ``harness_ab.py``,
``viz_server.py``.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Provide a key-shaped placeholder so the real client constructs.  It never leaves
# this process: the HTTP transport below intercepts every request.
os.environ.setdefault("TYPESAFE_API_KEY", "local-replay-not-a-real-key")

import httpx2  # noqa: E402

from typesafe_mario.actions import Action  # noqa: E402

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"


class ScriptedPilotTransport(httpx2.BaseTransport):
    """Answers system_one requests in the real wire format, from the state alone."""

    def __init__(self, *, delay_ms: float = 0.0) -> None:
        self.requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []
        self.delay_ms = delay_ms
        self._legitimate_payload = True

    # -- the pilot's judgement, derived only from the state payload -----------------
    @staticmethod
    def _decide(state: dict[str, Any]) -> tuple[str, dict[str, float]]:
        """A small reactive pilot, reading only the facts in its state payload.

        Terrain is judged on *projected* distance, not current distance.  The state
        publishes ``reaction_timing.total_reaction_horizon_frames`` precisely because a
        decision takes effect several frames later; at running speed the world advances
        more than a tile in that window, so a policy that jumps when the obstacle is
        already within three tiles takes off too late to clear a tall pipe.  The upstream
        instructions tell the model to use projections rather than distance alone — this
        pilot does the same arithmetic so it is testing the harness, not fighting it.
        """
        player = state.get("player", {})
        hazard = state.get("hazard", {})
        terrain = state.get("terrain", {})
        trajectory = state.get("trajectory", {})
        timing = state.get("reaction_timing", {})

        speed = abs(float(player.get("horizontal_speed_px_per_frame") or 0.0))
        speed = max(speed, 2.6)  # running speed is what a forward-jump macro produces
        horizon = float(timing.get("total_reaction_horizon_frames") or 0)
        advance_px = speed * horizon

        def projected(tiles_key: str) -> float | None:
            tiles = terrain.get(tiles_key)
            if tiles is None:
                return None
            return tiles * 16.0 - advance_px

        obstacle_px = projected("obstacle_distance_tiles")
        gap_px = projected("gap_distance_tiles")
        height_tiles = float(terrain.get("obstacle_height_tiles") or 0)

        # Consult the injected history before deciding how early to commit.  This is the
        # point of the memory: if an earlier attempt was lost just ahead while airborne,
        # that takeoff was too early, so require a nearer approach this time.
        cautious = False
        history = state.get("prior_attempts")
        if isinstance(history, dict):
            here = int(player.get("x") or 0)
            for death in history.get("deaths", []):
                if not isinstance(death, dict):
                    continue
                ahead = int(death.get("at_x") or 0) - here
                if death.get("airborne") and 0 < ahead <= 160:
                    cautious = True
                    break

        # A tall obstacle needs the takeoff earlier than a low one: the jump has to be at
        # full height by the time Mario reaches the wall.
        obstacle_trigger = 16.0 + 10.0 * height_tiles
        needed = (
            (obstacle_px is not None and obstacle_px <= obstacle_trigger)
            or (gap_px is not None and gap_px <= 16.0)
        )

        stalled = state.get("episode", {}).get("stalled_frames", 0)
        airborne_rising = (
            not player.get("grounded", True)
            and player.get("jump_phase") in {"rising", "apex"}
        )


        # `cautious` fires only while a remembered failure point is still some way off, so
        # there is room to re-approach.  Close to the hazard the live facts take over and
        # a jump is committed normally; the memory is advisory, never a substitute for what
        # the current state says.
        approach_px = min(
            [v for v in (obstacle_px, gap_px) if v is not None],
            default=None,
        )
        if cautious and approach_px is not None and 24.0 < approach_px <= 160.0:
            # A previous attempt was lost ahead while airborne: that takeoff was too early.
            # Rather than tune a threshold, change the approach — ease off and re-enter
            # with a fresh run-up, which is what a person does after mistiming a jump.
            pick = Action.LEFT
        elif hazard.get("jump_must_start_this_decision") or hazard.get(
            "contact_within_reaction_horizon"
        ):
            pick = Action.RIGHT_RUN_JUMP
        elif needed or terrain.get("obstacle_ahead") or terrain.get("gap_ahead"):
            # Only commit from the ground; mid-air the held jump continues the arc.
            pick = Action.RIGHT_RUN_JUMP
        elif trajectory.get("crossing_known_gap") or airborne_rising:
            pick = Action.RIGHT_RUN_JUMP
        elif stalled >= 3:
            # Wedged against something: hop to get over it.
            pick = Action.RIGHT_RUN_JUMP
        else:
            pick = Action.RIGHT_RUN

        probabilities = {action.value: 0.02 for action in Action}
        probabilities[pick.value] = 0.88
        total = sum(probabilities.values())
        probabilities = {name: value / total for name, value in probabilities.items()}
        return pick.value, probabilities

    @staticmethod
    def _jump_needed(state: dict[str, Any]) -> float:
        hazard = state.get("hazard", {})
        terrain = state.get("terrain", {})
        if hazard.get("jump_must_start_this_decision"):
            return 0.97
        if hazard.get("contact_within_reaction_horizon") or terrain.get("obstacle_ahead"):
            return 0.9
        if terrain.get("gap_ahead") or terrain.get("gap_distance_tiles") is not None:
            return 0.72
        return 0.05

    @staticmethod
    def _danger(state: dict[str, Any]) -> tuple[float, dict[str, float]]:
        hazard = state.get("hazard", {})
        terrain = state.get("terrain", {})
        if hazard.get("jump_must_start_this_decision") or hazard.get(
            "contact_within_reaction_horizon"
        ):
            return 2.0, {0: 0.05, 1: 0.15, 2: 0.80}
        if terrain.get("obstacle_ahead") or terrain.get("gap_ahead"):
            return 1.0, {0: 0.20, 1: 0.60, 2: 0.20}
        return 0.0, {0: 0.90, 1: 0.08, 2: 0.02}

    # -- wire handling -------------------------------------------------------------
    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        payload = json.loads(request.content or b"{}")
        questions = payload.get("questions", {})
        state = payload.get("state", {})

        if not isinstance(state, dict):
            raise AssertionError("upstream must send the structured state object")

        choice, probabilities = self._decide(state)
        noul = self._jump_needed(state)
        score, score_probabilities = self._danger(state)

        # The criteria a real request carries must line up with the answers we return.
        criteria = questions.get("next_action", {}).get("criteria", {})
        assert set(criteria) == {action.value for action in Action}, (
            f"Choice criteria drifted from the action set: {sorted(criteria)}"
        )
        assert choice in criteria, f"scripted pick {choice!r} is not a legal criterion"

        answer = {
            "model": "scripted-pilot (NOT Jev — local replay stand-in)",
            "usage": {"input_tokens": len(str(state)), "output_tokens": 12},
            "answers": {
                "next_action": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": 0.88,
                    "probabilities": probabilities,
                },
                "jump_needed": {"type": "noul", "noul": noul},
                "danger": {
                    "type": "score",
                    "score": score,
                    "confidence": 0.85,
                    "legend": {
                        0: "Safe open movement",
                        1: "Potential obstacle or enemy soon",
                        2: "Immediate collision, fall, or enemy threat",
                    },
                    "probabilities": score_probabilities,
                },
            },
        }
        self.requests.append(payload)
        self.responses.append(answer)
        return httpx2.Response(200, json=answer)


@contextmanager
def patched_client(transport: httpx2.BaseTransport, memory=None):
    """Make TypeSafePolicy build a real client that talks to our transport.

    When ``memory`` is supplied, the outgoing ``state`` object gains a
    ``prior_attempts`` block describing earlier deaths.  The upstream policy is untouched:
    the merge happens here, at the boundary where the request is actually built, so the
    same mechanism would work against the real API without any other change.
    """
    import typesafe_sdk

    real_client = typesafe_sdk.TypeSafeClient

    class BoundClient(real_client):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            kwargs.setdefault("api_key", "local-replay-not-a-real-key")
            kwargs.setdefault("retry", typesafe_sdk.RetryPolicy(max_retries=0))
            super().__init__(*args, **kwargs)

        def system_one(self, state, questions, **kwargs):  # type: ignore[override]
            if memory is not None and isinstance(state, dict):
                history = memory.as_context()
                if history is not None:
                    state = {**state, "prior_attempts": history}
            return super().system_one(state, questions, **kwargs)

    typesafe_sdk.TypeSafeClient = BoundClient
    try:
        yield
    finally:
        typesafe_sdk.TypeSafeClient = real_client


def summarise(log_path: Path) -> dict[str, Any]:
    records = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    if not records:
        return {"decisions": 0}
    actions: dict[str, int] = {}
    for record in records:
        actions[record["action"]] = actions.get(record["action"], 0) + 1
    last = records[-1]
    latencies = [r["latency_ms"] for r in records if r.get("latency_ms")]
    # The terminal outcome lands in the `terminated` flag of the final record: each record
    # stores the state observed *before* its action batch runs, so a stage clear during
    # that batch never appears as a state, only as this flag.
    terminated = bool(last.get("terminated"))
    died = bool(last["state"]["episode"]["dead"])
    cleared = bool(last["state"]["episode"]["stage_clear"]) or (
        terminated and not died and last.get("reward", 0.0) >= 100.0
    )
    return {
        "decisions": len(records),
        "first_x": records[0]["state"]["player"]["x"],
        "best_x": max(r["state"]["episode"]["best_progress"] for r in records),
        "final_x": last["state"]["player"]["x"],
        "died": died,
        "cleared": cleared,
        "ended_reason": "stage_clear" if cleared else ("death" if died else "budget_exhausted"),
        "actions": dict(sorted(actions.items(), key=lambda item: -item[1])),
        "jump_must_start_triggers": sum(
            1 for r in records if r["state"]["hazard"]["jump_must_start_this_decision"]
        ),
        "crossing_gap_frames": sum(
            1 for r in records if r["state"]["trajectory"]["crossing_known_gap"]
        ),
        "latency_ms_median": sorted(latencies)[len(latencies) // 2] if latencies else None,
        "log": str(log_path.relative_to(HERE)),
    }
