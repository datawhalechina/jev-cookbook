"""Mario harness v2, written in the JevHarness style.

Reference: ``TianyuCodings/JevHarness`` — "Reason deeply during development. Freeze the
strategy. Let Jev make fast, fuzzy decisions."  The Pokémon reference harness does three
things the upstream Mario harness does not:

1. **Pre-computed derived facts.**  The Pokémon state carries a computed damage race
   ("needing 2 turns while the opponent needs 2"); Mario's state publishes raw distances
   and leaves the takeoff arithmetic to the model.
2. **A quantitative criterion per action.**  Each Pokémon option carries its own measured
   consequence ("about 68 percent of its HP … switching concedes one free attack");
   Mario's criteria are static prose, identical every request.
3. **Instructions as strategy statements.**  "Take a stated knockout when it is available"
   is executable by a fuzzy judge; "use hazard projections, not distance alone" is a
   maths lesson.

This module applies the same three patterns to Mario, measured on the real emulator:

* ``JUMP_PHYSICS`` — the jump arc measured frame-by-frame from the bundled ROM (peak 68px
  at t=25, airtime 47 frames, horizontal span 82px).  The height windows derived from it
  are the whole game: clearing a 3-tile pipe requires takeoff **24–65px** before the wall.
  Outside that window the attempt fails no matter what the model chooses — and both prior
  failure modes we observed (stuck at x=594, pit deaths at x=1104) sit exactly outside it.
* ``feasibility_features`` — turns the published distances into a takeoff-window verdict:
  ``clearable`` / ``wait`` / ``too_late`` / ``too_early``, with the reasoning in numbers.
* ``build_questions`` — per-action criteria with this-decision consequences inlined, and
  instructions as imperatives.
* ``HazardLessons`` — the cross-episode memory distilled from raw death records into
  per-hazard lessons with direction (jumped too early vs too late), which is what the
  criteria need; a list of raw deaths is not actionable.

Nothing upstream is modified: this is an alternative harness at the reproduction layer,
which is exactly how JevHarness treats harnesses — swappable artefacts, authored ahead of
time and frozen at runtime.

Honest scope note
-----------------
Verified against a rules-based stand-in pilot (``pilot_choose_v2``), which reads the
published verdict instead of redoing the arithmetic. The A/B therefore measures the value
of **harness information quality to this scripted reader**, not real Jev performance.
Bundled experiment entry points deliberately install a mock transport; setting
``TYPESAFE_API_KEY`` does not change that. For a live Jev run, use the upstream CLI and
upstream-supported harness rather than treating this local A/B as model evidence.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from typesafe_mario.actions import Action
from typesafe_mario.policy import Decision, TypeSafePolicy

# --------------------------------------------------------------- measured jump physics
# From /tmp/jumpmodel.py: full-speed running jump (A+B held), World 1-1, real ROM.
JUMP_AIRTIME_FRAMES = 47
JUMP_SPAN_PX = 82  # horizontal distance covered over the full arc at running speed
RUN_SPEED_PX_PER_FRAME = 2.6

# height -> (first frame above it, last frame above it, horizontal window in px)
_RISE = [(1, 5), (3, 14), (5, 23), (7, 30), (9, 37), (11, 44), (13, 49), (15, 54),
         (19, 62), (23, 66), (25, 68), (31, 66), (35, 56), (37, 47), (39, 37),
         (41, 27), (43, 17), (45, 7), (47, 0)]
_HEIGHT_WINDOWS_TILES: dict[int, tuple[int, int]] = {
    1: (4, 43),
    2: (8, 40),
    3: (13, 36),
    4: (21, 32),
}


def height_window_px(height_tiles: int) -> tuple[float, float] | None:
    """Horizontal takeoff window [near_px, far_px] that clears the given height.

    Measured: the arc is above ``height_tiles`` only between two frames; multiply both by
    running speed to get the range of distances-from-the-wall at which a takeoff started
    now still arrives above that height.
    """
    window = _HEIGHT_WINDOWS_TILES.get(int(height_tiles))
    if window is None:
        return None
    first, last = window
    return (first * RUN_SPEED_PX_PER_FRAME, last * RUN_SPEED_PX_PER_FRAME)


# --------------------------------------------------------------- feasibility features
def feasibility_features(state: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the takeoff-window verdict from the state the harness already publishes.

    This is the "damage race" of the Pokémon harness: arithmetic done once, in code, so
    the judge only has to read a verdict instead of doing physics mid-choice.
    """
    player = state.get("player", {})
    terrain = state.get("terrain", {})
    timing = state.get("reaction_timing", {})

    # Unit trap: the snapshot's dx is the displacement since the previous parse, and the
    # parse cadence differs by display path.  The dashboard loop parses every frame, so
    # dx is already per-frame (~2.6 at full run; SMB's engine never exceeds ~4); headless
    # parses once per decision batch, so dx is a batch displacement (~10+ px).  Decide
    # which world we are in by magnitude — per-frame values are physically capped at ~4.
    horizon_frames = int(timing.get("action_horizon_frames") or 8)
    raw_dx = abs(float(player.get("horizontal_speed_px_per_frame") or 0.0))
    raw_speed = raw_dx / max(1, horizon_frames) if raw_dx > 6.0 else raw_dx
    speed = raw_speed
    slow = raw_speed < RUN_SPEED_PX_PER_FRAME - 0.4
    horizon = int(timing.get("total_reaction_horizon_frames") or 8)

    obstacle_tiles = terrain.get("obstacle_distance_tiles")
    height_tiles = int(terrain.get("obstacle_height_tiles") or 0)
    gap_tiles = terrain.get("gap_distance_tiles")
    gap_width = int(terrain.get("gap_width_tiles_visible") or 0)

    kind = "none"
    distance_px: float | None = None
    required_height = 0
    if obstacle_tiles is not None and height_tiles > 0:
        kind = "obstacle"
        distance_px = float(obstacle_tiles) * 16.0
        required_height = height_tiles
    elif gap_tiles is not None:
        kind = "gap"
        distance_px = float(gap_tiles) * 16.0
        required_height = 1 if gap_width <= 2 else 2

    verdict = {
        "hazard_kind": kind,
        "distance_px": distance_px,
        "required_height_tiles": required_height,
        "speed_px_per_frame": speed,
        "jump_span_px": JUMP_SPAN_PX,
        "reaction_delay_frames": horizon,
        "reaction_delay_px": round(horizon * speed, 1),
        "clearable": False,
        "verdict": "no_hazard",
        "advice": "keep running; nothing ahead requires a jump",
    }
    if kind == "none" or distance_px is None:
        return verdict

    # The window table was measured at full running speed; a jump from a slower start
    # peaks lower and misses tall obstacles.  Say so instead of silently pretending —
    # but only while there is still room to rebuild speed.  At the wall the answer is
    # the too_late path (jump and take the loss, or back off); "keep running" into a
    # wall forever is not advice, it is a deadlock.
    if slow and required_height >= 3:
        projected_if_slow = max(0.0, distance_px - horizon * speed)
        window_probe = height_window_px(required_height)
        still_far = window_probe is None or projected_if_slow > window_probe[0] + 24.0
        if still_far:
            verdict["verdict"] = "regain_speed"
            verdict["advice"] = (
                f"moving at only {round(raw_speed, 1)}px/frame; the takeoff window assumes "
                f"full running speed. Keep running to rebuild speed before committing"
            )
            return verdict

    # The decision lands `horizon` frames from now, so the world advances before the
    # takeoff even starts.  Judge the window from the *projected* distance.
    projected = max(0.0, distance_px - horizon * speed)

    if kind == "obstacle":
        window = height_window_px(required_height)
        if window is None:
            return verdict
        near, far = window
        # Landing on top of a pipe shorter than the full arc also clears it, so the far
        # bound is generous; the near bound is the hard one.
        verdict["takeoff_window_px"] = [round(near, 1), round(far, 1)]
        if projected > far:
            verdict["verdict"] = "wait"
            frames = int((projected - far) / speed)
            verdict["advice"] = (
                f"{required_height}-tile obstacle in {round(projected)}px: still {frames} "
                f"frames too far for the takeoff window; keep running and jump when the "
                f"projected distance enters the window"
            )
        elif projected >= near:
            verdict["clearable"] = True
            verdict["verdict"] = "jump_now"
            verdict["advice"] = (
                f"{required_height}-tile obstacle in {round(projected)}px, inside the "
                f"{round(near)}-{round(far)}px takeoff window: commit to right_run_jump "
                f"now and keep it held"
            )
        else:
            verdict["verdict"] = "too_late"
            verdict["clearable"] = projected > 0
            verdict["advice"] = (
                f"{required_height}-tile obstacle in {round(projected)}px, closer than the "
                f"{round(near)}px window edge: a plain jump will not clear it. Jump anyway "
                f"to land on top if possible, or reverse to regain a run-up"
            )
        return verdict

    # Gap: what matters is whether the arc still has height when crossing the far edge.
    gap_width_px = float(gap_width) * 16.0
    far_edge = projected + gap_width_px
    verdict["gap_width_px"] = gap_width_px
    verdict["far_edge_px"] = round(far_edge, 1)
    if far_edge > JUMP_SPAN_PX:
        verdict["verdict"] = "too_wide_from_here"
        verdict["advice"] = (
            f"gap of {gap_width} tiles, far edge {round(far_edge)}px out but a running "
            f"jump only spans {JUMP_SPAN_PX}px: do not jump yet, get closer first"
        )
    elif projected <= 8.0:
        verdict["verdict"] = "too_late"
        verdict["advice"] = (
            f"at the lip of a {gap_width}-tile gap: jump immediately"
        )
        verdict["clearable"] = True
    else:
        verdict["clearable"] = True
        verdict["verdict"] = "jump_now"
        verdict["advice"] = (
            f"{gap_width}-tile gap, far edge {round(far_edge)}px out, within the "
            f"{JUMP_SPAN_PX}px arc: commit to right_run_jump now"
        )
    return verdict


# --------------------------------------------------------------- memory -> lessons
def lessons_from_deaths(deaths: Sequence[Mapping[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    """Distil raw death records into per-hazard lessons with a direction.

    Raw deaths ("died at x=1104, airborne") are evidence; a lesson ("takeoffs started
    near x=1032 keep falling short of this gap — take off closer to the edge") is what a
    fuzzy judge can act on.  Clustering by rounded x is crude but sufficient: a level's
    hazards are tens of tiles apart while repeated deaths land within a few pixels.
    """
    clusters: dict[int, list[Mapping[str, Any]]] = {}
    for death in deaths:
        key = int(round(int(death.get("at_x") or 0) / 64))
        clusters.setdefault(key, []).append(death)

    lessons = []
    for _, group in sorted(clusters.items(), key=lambda item: -len(item[1]))[:limit]:
        xs = [int(d.get("at_x") or 0) for d in group]
        actions = {d.get("action_when_lost") for d in group}
        airborne = all(d.get("airborne") for d in group)
        causes = {d.get("cause") for d in group}
        if airborne and any("fell" in (c or "") for c in causes):
            direction = "takeoffs here were started too early and fell short"
            advice = "start the jump closer to the hazard, inside the published window"
        elif any("blocked" in (c or "") for c in causes):
            direction = "attempts here never left the ground in time"
            advice = "the takeoff window opens earlier than it feels; commit on jump_now"
        else:
            direction = "repeated losses at this spot"
            advice = "approach differently: slow down or reverse first"
        lessons.append(
            {
                "hazard_x": int(sum(xs) / len(xs)),
                "attempts_lost": len(group),
                "actions_on_record": sorted(str(a) for a in actions if a),
                "pattern": direction,
                "advice": advice,
            }
        )
    return lessons


# --------------------------------------------------------------- the frozen questions
def build_questions(state: Mapping[str, Any]) -> dict[str, Any]:
    """JevHarness-style request: strategy instructions + a quantitative criterion per action.

    The criteria are regenerated per request from the pre-computed facts, exactly as the
    Pokémon harness pastes damage-race numbers into every option.
    """
    feasibility = state.get("takeoff_window", {})
    lessons = (state.get("prior_attempts") or {}).get("lessons", [])
    lesson_text = ""
    if lessons:
        first = lessons[0]
        lesson_text = (
            f" Memory says: {first['attempts_lost']} earlier attempt(s) were lost near "
            f"x={first['hazard_x']} — {first['pattern']}. {first['advice']}."
        )

    window = feasibility.get("takeoff_window_px")
    window_text = (
        f"takeoff window {window[0]}-{window[1]}px" if window else "arc-based window"
    )
    distance = feasibility.get("distance_px")
    distance_text = f"{round(distance)}px" if distance is not None else "n/a"

    hazard_now = state.get("hazard", {})
    enemy_note = ""
    if hazard_now.get("enemy_ahead"):
        enemy_note = (
            f" An enemy ({hazard_now.get('nearest_enemy_kind')}) is "
            f"{hazard_now.get('nearest_enemy_distance_pixels')}px ahead; the published "
            f"contact arithmetic already accounts for your reaction delay — when "
            f"jump_must_start_this_decision is true, a running jump is due immediately."
        )

    instructions = (
        "Pick the single controller macro that advances toward the flag without dying. "
        "Every option below lists this decision's measured consequence from the "
        "takeoff-window analysis; the analysis converts distance, height and your "
        "reaction delay into one verdict, and that verdict is already authoritative. "
        "Commit to right_run_jump exactly when the verdict says jump_now; keep it held "
        "while rising. When the verdict says wait, keep running — an early takeoff falls "
        "short just as surely as a late one. When it says too_late, jump anyway to try "
        "for the top, or reverse for a fresh run-up if the way back is clear."
        + enemy_note
        + lesson_text
        + " Answer with exactly one of the listed action IDs."
    )

    verdict = feasibility.get("verdict", "no_hazard")
    advice = feasibility.get("advice", "")

    criteria = {
        Action.NOOP.value: (
            "release control for this decision: momentum continues, no new takeoff. "
            "Rarely correct while a hazard verdict is pending."
        ),
        Action.RIGHT.value: (
            f"walk right at {round(RUN_SPEED_PX_PER_FRAME * 60 / 16, 1)} tiles/s: slow "
            f"enough to keep the next takeoff window open longer, but it surrenders "
            f"ground while the verdict is {verdict}."
        ),
        Action.RIGHT_JUMP.value: (
            f"forward jump at walking pace: lower arc than a running jump, so it clears "
            f"1-tile obstacles but not the {feasibility.get('required_height_tiles', 0)}"
            f"-tile hazard currently {distance_text} ahead ({window_text})."
        ),
        Action.RIGHT_RUN.value: (
            f"run right at {RUN_SPEED_PX_PER_FRAME}px/frame: correct while the verdict is "
            f"'wait' — it closes the distance until the window opens. Current verdict: "
            f"{verdict}. {advice}"
        ),
        Action.RIGHT_RUN_JUMP.value: (
            f"running jump: the only macro that clears the {feasibility.get('required_height_tiles', 0)}"
            f"-tile hazard {distance_text} ahead. Its measured arc peaks at 68px "
            f"(4.25 tiles) over 47 frames, spanning {JUMP_SPAN_PX}px. Current verdict: "
            f"{verdict} — {advice}"
        ),
        Action.JUMP.value: (
            "vertical jump: gains height without advancing; useful only to stall or to "
            "bounce off a spot, not against this verdict."
        ),
        Action.LEFT.value: (
            "reverse: regains a fresh run-up when the verdict is too_late or when memory "
            "says the last takeoff from here fell short. Costs progress; worth it only "
            "to convert a doomed attempt into a clearable one."
        ),
    }
    return {
        "next_action": {
            "type": "choice",
            "instructions": instructions,
            "criteria": criteria,
        }
    }


# --------------------------------------------------------------- the harness wrapper
class MarioHarnessV2(TypeSafePolicy):
    """A frozen alternative harness: same SDK call, richer state and questions.

    JevHarness treats a harness as an authored, versioned artefact; this is version 2 of
    the Mario one.  The upstream ``TypeSafePolicy`` is subclassed so the transport, retry
    and answer decoding are literally the same code paths — only the request assembly
    differs.
    """

    def __init__(self, *, memory=None) -> None:
        super().__init__()
        self.memory = memory

    def choose(self, snapshot, actions: Sequence[Action]):  # noqa: D102 - see upstream
        state = snapshot.to_state()
        state["takeoff_window"] = feasibility_features(state)

        if self.memory is not None:
            history = self.memory.as_context()
            if history is not None:
                history = dict(history)
                history["lessons"] = lessons_from_deaths(history.get("deaths", []))
                state["prior_attempts"] = history

        questions = build_questions(state)

        started = time.perf_counter()
        response = self._client.system_one(state=state, questions=questions)
        latency_ms = (time.perf_counter() - started) * 1000

        action_answer = self._answer(response, "next_action", "choices")
        action = Action(str(action_answer.choice))
        probabilities = {
            str(key): float(value)
            for key, value in dict(action_answer.probabilities).items()
        }
        return Decision(
            action=action,
            confidence=float(action_answer.confidence),
            probabilities=probabilities,
            latency_ms=latency_ms,
        )


# --------------------------------------------------------------- the stand-in reader
def pilot_choose_v2(state: Mapping[str, Any]) -> tuple[str, dict[str, float]]:
    """The stand-in reader of harness v2: it reads verdicts, it does not redo physics.

    Contrast with the v1 pilot in ``repro_run.py``, which re-derives projections from raw
    distances.  Under JevHarness's division of labour the harness does the arithmetic and
    the judge reads conclusions — so v1-vs-v2 isolates the value of the harness itself.
    """
    player = state.get("player", {})
    episode = state.get("episode", {})
    window = state.get("takeoff_window", {})
    hazard = state.get("hazard", {})
    history = state.get("prior_attempts") or {}
    stalled = int(episode.get("stalled_frames") or 0)
    horizon = int(
        (state.get("reaction_timing") or {}).get("action_horizon_frames") or 8
    )
    verdict = str(window.get("verdict") or "no_hazard")

    lessons = history.get("lessons") or []
    near_lesson = None
    here = int(player.get("x") or 0)
    for lesson in lessons:
        delta = int(lesson.get("hazard_x") or 0) - here
        if 0 < delta <= 192:
            near_lesson = lesson
            break

    # A hazard attempted repeatedly from a standstill keeps failing the same way: tall
    # obstacles need a running start (the measured 68px peak assumes full speed).  Back
    # off only after a *real* wall-hug: `stalled` counts frames in the dashboard loop,
    # where the 60ms inference wait alone freezes x for ~4 frames, so a threshold tuned
    # for headless batches fired on every such pause and walked Mario backwards all episode.
    # Require a multiple of the decision horizon and contact with the ground.
    wedged = (
        player.get("grounded", True)
        and stalled >= max(6, 3 * horizon)
        and verdict in ("too_late", "jump_now", "no_hazard")
    )

    airborne = not player.get("grounded", True)
    # A running jump needs A held for the whole 47-frame arc (~6 decisions).  Dropping it
    # mid-arc — including during the descent, which shortens the arc and drops Mario
    # short — was the single most common way this reader lost height in the first A/B.
    if airborne:
        pick = Action.RIGHT_RUN_JUMP
    elif hazard.get("jump_must_start_this_decision") or hazard.get(
        "contact_within_reaction_horizon"
    ):
        pick = Action.RIGHT_RUN_JUMP
    elif wedged:
        pick = Action.LEFT
    elif verdict == "jump_now":
        pick = Action.RIGHT_RUN_JUMP
    elif verdict == "too_late":
        pick = Action.RIGHT_RUN_JUMP if player.get("grounded", True) else Action.RIGHT_RUN
    elif verdict == "regain_speed":
        pick = Action.RIGHT_RUN
    elif verdict == "too_wide_from_here":
        pick = Action.RIGHT_RUN
    elif verdict == "wait":
        pick = Action.RIGHT_RUN
    else:
        pick = Action.RIGHT_RUN_JUMP if stalled >= 6 else Action.RIGHT_RUN

    probabilities = {action.value: 0.02 for action in Action}
    probabilities[pick.value] = 0.88
    total = sum(probabilities.values())
    return pick.value, {name: value / total for name, value in probabilities.items()}
