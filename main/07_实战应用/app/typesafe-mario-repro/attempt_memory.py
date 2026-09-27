"""Cross-episode memory extension for the Mario decision state.

Why this lives in the harness rather than the policy
----------------------------------------------------
The upstream ``TypeSafePolicy`` builds one request per decision from the current snapshot
only; it has no notion of previous attempts.  Adding memory therefore must not touch the
upstream files.  It is injected one layer above them, by wrapping the SDK client's
``system_one`` and merging an extra key into the outgoing ``state`` object.  TypeSafe
accepts arbitrary JSON as state, so a real policy could receive its own history as
additional context. In this reproduction, however, the experiment entry points route
requests to ``ScriptedPilotTransport``; the local pilot receives this state and no Jev
API call is made.

What is recorded
----------------
The request payload as it was handed to the local transport, not a reconstruction: the
transport keeps the last few payloads verbatim, and a death stores the most recent one along
with the outcome. This keeps the local replay auditable rather than summarised after the fact.

What the added state contains
-----------------------------
A ``prior_attempts`` block, clearly labelled as history so it cannot be mistaken for the
current situation. Each death carries the position, the action that was being committed to,
the published facts that were on the table (terrain, hazard, jump phase), and a short trace
of the final decisions. In the bundled browser and experiment path this is context for the
scripted pilot, not evidence that Jev received or used it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

MAX_TRACE_DECISIONS = 8


@dataclass
class PromptSnapshot:
    """One state payload handed to the configured transport."""

    state: dict[str, Any]
    chosen: str | None = None


@dataclass
class DeathRecord:
    """One failed attempt, recorded from the state exposed to the policy."""

    episode: int
    at_x: int
    at_y: int
    action: str | None
    grounded: bool
    jump_phase: str
    gap_distance_tiles: int | None
    obstacle_distance_tiles: int | None
    nearest_enemy: str | None
    cause: str
    trace: list[dict[str, Any]] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        """The compact history block added to subsequent state payloads."""
        return {
            "at_x": self.at_x,
            "at_y": self.at_y,
            "action_when_lost": self.action,
            "airborne": not self.grounded,
            "jump_phase": self.jump_phase,
            "terrain_gap_tiles": self.gap_distance_tiles,
            "terrain_obstacle_tiles": self.obstacle_distance_tiles,
            "nearest_enemy": self.nearest_enemy,
            "cause": self.cause,
            "final_decisions": self.trace,
        }


class AttemptMemory:
    """Accumulates episode outcomes and renders them as additional state context."""

    def __init__(self, max_deaths: int = 6) -> None:
        self._recent_prompts: deque[PromptSnapshot] = deque(maxlen=MAX_TRACE_DECISIONS)
        self.deaths: list[DeathRecord] = []
        self.clears: list[dict[str, Any]] = []
        self.episodes = 0
        self.max_deaths = max_deaths
        self.enabled = True

    # ------------------------------------------------------------------ recording
    def observe_request(self, state: dict[str, Any]) -> PromptSnapshot:
        """Keep the outgoing payload verbatim; the last one before death is the lesson.

        The chosen action is not known when the request goes out — it is the answer — so
        the returned snapshot is filled in by :meth:`note_choice` once the reply lands.
        """
        snapshot = PromptSnapshot(state=state)
        self._recent_prompts.append(snapshot)
        return snapshot

    def note_choice(self, chosen: str) -> None:
        """Attach the configured policy/transport's answer to the recorded request."""
        if self._recent_prompts:
            self._recent_prompts[-1].chosen = chosen

    def start_episode(self) -> None:
        """Begin a new attempt: count it and drop the previous attempt's trace.

        The trace must not span attempts, otherwise a death would be explained by
        decisions from an earlier run and the lesson handed back would be fiction.
        """
        self.episodes += 1
        self._recent_prompts.clear()

    @staticmethod
    def _classify(state: dict[str, Any]) -> str:
        """Name the likely cause from the facts that were published, not from hindsight."""
        player = state.get("player", {})
        hazard = state.get("hazard", {})
        terrain = state.get("terrain", {})
        grounded = bool(player.get("grounded", True))
        if not grounded and player.get("jump_phase") in {"falling", "airborne"}:
            return "fell after a jump did not reach safe ground"
        if hazard.get("contact_within_reaction_horizon"):
            return "enemy contact"
        if terrain.get("gap_ahead") or terrain.get("gap_distance_tiles") is not None:
            return "lost footing at a gap"
        if terrain.get("obstacle_ahead"):
            return "blocked by an obstacle"
        return "unknown"

    def note_death(self, outcome: dict[str, Any]) -> DeathRecord | None:
        """Record a death from the last state exposed to the policy, plus its outcome.

        ``outcome`` carries the live position at the end of the episode; the published
        facts come from the stored payload, because those are the facts the configured
        policy path was given. In bundled runs that path is the local scripted pilot.
        """
        last = self._recent_prompts[-1] if self._recent_prompts else None
        state = dict(last.state) if last else {}

        player = state.get("player", {})
        terrain = state.get("terrain", {})
        hazard = state.get("hazard", {})
        trace = [
            {
                "x": snap.state.get("player", {}).get("x"),
                "action": snap.chosen,
                "airborne": not snap.state.get("player", {}).get("grounded", True),
                "jump_phase": snap.state.get("player", {}).get("jump_phase"),
                "gap_tiles": snap.state.get("terrain", {}).get("gap_distance_tiles"),
            }
            for snap in list(self._recent_prompts)[-MAX_TRACE_DECISIONS:]
        ]

        record = DeathRecord(
            episode=self.episodes,
            at_x=int(outcome.get("x") or player.get("x") or 0),
            at_y=int(outcome.get("y") or player.get("y") or 0),
            action=last.chosen if last else None,
            grounded=bool(player.get("grounded", True)),
            jump_phase=str(player.get("jump_phase") or "unknown"),
            gap_distance_tiles=terrain.get("gap_distance_tiles"),
            obstacle_distance_tiles=terrain.get("obstacle_distance_tiles"),
            nearest_enemy=hazard.get("nearest_enemy_kind"),
            cause=self._classify(state),
            trace=trace,
        )
        self.deaths.append(record)
        self.deaths = self.deaths[-self.max_deaths :]
        return record

    def note_clear(self, outcome: dict[str, Any]) -> None:
        self.clears.append({"at_x": int(outcome.get("x") or 0), "episode": self.episodes})

    def record_death_fields(
        self,
        *,
        at_x: int,
        at_y: int = 0,
        action_when_lost: str | None = None,
        airborne: bool = False,
        jump_phase: str = "unknown",
        gap_distance_tiles: int | None = None,
        obstacle_distance_tiles: int | None = None,
        nearest_enemy: str | None = None,
        cause: str = "unknown",
        final_decisions: list[dict[str, Any]] | None = None,
    ) -> DeathRecord:
        """Record a death from plain fields, for headless runs with no prompt trace."""
        record = DeathRecord(
            episode=self.episodes,
            at_x=int(at_x),
            at_y=int(at_y),
            action=action_when_lost,
            grounded=not airborne,
            jump_phase=jump_phase,
            gap_distance_tiles=gap_distance_tiles,
            obstacle_distance_tiles=obstacle_distance_tiles,
            nearest_enemy=nearest_enemy,
            cause=cause,
            trace=final_decisions or [],
        )
        self.deaths.append(record)
        self.deaths = self.deaths[-self.max_deaths :]
        return record

    # ------------------------------------------------------------------ playback
    def as_context(self) -> dict[str, Any] | None:
        """The ``prior_attempts`` block merged into the next request's state."""
        if not self.enabled or (not self.deaths and not self.clears):
            return None
        return {
            "note": (
                "History of earlier attempts at this level, provided as a reference. This "
                "is NOT the current situation: the `hazard` and `terrain` keys above "
                "describe the present moment and must take precedence. Use this history "
                "only to avoid repeating a failed approach."
            ),
            "attempts_so_far": self.episodes,
            "cleared_before": bool(self.clears),
            "clear_positions": [c["at_x"] for c in self.clears][-3:],
            "deaths": [record.to_context() for record in self.deaths],
        }

    def danger_zone(self) -> tuple[int, int] | None:
        """The x-range where deaths cluster, if any — a cheap summary any policy can use."""
        if not self.deaths:
            return None
        xs = [record.at_x for record in self.deaths]
        return (min(xs), max(xs))

    def failed_at(self, x: int, *, tolerance: int = 96) -> list[DeathRecord]:
        """Deaths recorded near ``x``, nearest first."""
        near = [record for record in self.deaths if abs(record.at_x - x) <= tolerance]
        return sorted(near, key=lambda record: abs(record.at_x - x))
