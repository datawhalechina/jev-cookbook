"""Serve the typesafe-mario decision loop as a local web visualization.

What runs here
--------------
The browser wrapper uses the upstream runner, emulator and dashboard protocol, but it
also installs the local ``CorrectedParser`` and ``MarioHarnessV2`` extensions.  The
``LiveDashboard`` is replaced by :class:`WebDashboard`, which publishes the frame and
telemetry to a browser.  The model HTTP hop is always replaced by a scripted local pilot;
this entry point does not call Jev and labels all decision values as mock.

Endpoints
---------
``GET  /``                the page
``GET  /frame.rgba``      the current emulator frame, raw RGBA (256x240, no encoding cost)
``GET  /state.json``      telemetry for the current decision
``GET  /model_input.json`` the exact state object sent to the local pilot adapter
``GET  /history.json``    one entry per decision, for the progress chart
``GET  /snapshot.png``    the current frame as a PNG
``POST /control``         ``{"command": "restart"|"pause"|"resume"|"quit", "fps": 30}``

Run:  ../typesafe-mario/.venv/bin/python viz_server.py --port 8770
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import threading
import time
import webbrowser
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("TYPESAFE_API_KEY", "local-replay-not-a-real-key")

import numpy as np  # noqa: E402

import typesafe_mario.runner as runner_module  # noqa: E402
from attempt_memory import AttemptMemory  # noqa: E402
from mario_harness_v2 import MarioHarnessV2, pilot_choose_v2  # noqa: E402
from parser_fix import CorrectedParser  # noqa: E402
from repro_run import ScriptedPilotTransport, patched_client  # noqa: E402
from typesafe_mario.actions import ACTION_DESCRIPTIONS, Action  # noqa: E402
from typesafe_mario.dashboard import DashboardCommand  # noqa: E402

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts" / "viz"
# Unknown until the level is actually finished: World 1-1 is far longer than the
# synthetic world, so the flag is recorded from the first clear rather than guessed.
FLAG_X_UNKNOWN = None
MAX_DECISIONS = 100_000  # the level ends on its own; the budget is only a runaway guard


# --------------------------------------------------------------------------- PNG writer
def png_bytes(rgba: np.ndarray) -> bytes:
    """Encode an HxWx4 uint8 array as a PNG using only the standard library."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    height, width = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------- shared hub
class VizHub:
    """State shared between the decision-loop thread and the HTTP server."""

    def __init__(
        self,
        *,
        fps: float,
        latency_ms: float,
        frames_per_decision: int,
        env_kind: str = "real",
        env_id: str = "SuperMarioBros-1-1-v0",
    ) -> None:
        self.lock = threading.Lock()
        self.fps = fps
        self.latency_ms = latency_ms
        self.frames_per_decision = frames_per_decision
        self.env_kind = env_kind
        self.env_id = env_id
        self.frame_rgba: bytes | None = None
        self.snapshot_rgba: np.ndarray | None = None
        self.width = 0
        self.height = 0
        self.telemetry: dict = {"status": "starting"}
        self.history: list[dict] = []
        self.model_input: dict | None = None
        self.requested: str | None = None
        self.paused = threading.Event()
        self.run_ended = False
        self.reset_count = 0
        self.started_at = time.time()
        self.episodes: list[dict] = []
        self.auto_restart = True
        self.auto_restart_seconds = 2.0
        self._ended_at: float | None = None
        # Level knowledge accumulates across episodes: the NES only exposes a 256px window,
        # so the map is stitched together from what each frame revealed.  Death marks use
        # the same coordinates, which is what makes "where does it keep dying" answerable.
        self.level_tiles: dict[int, dict[int, bool]] = {}
        self.level_max_col = 0
        self.level_min_col = 0
        self.death_marks: list[dict] = []
        self.clear_marks: list[dict] = []
        self.flag_x: int | None = None
        # What earlier attempts looked like to the local pilot, replayed into later prompts.
        self.memory = AttemptMemory()
        self.memory_enabled = True

    def observe_grid(self, columns: list[tuple[int, int, bool]]) -> None:
        """Fold one frame's worth of (column, row, solid) triples into the level map."""
        with self.lock:
            for column, row, solid in columns:
                self.level_tiles.setdefault(column, {})[row] = solid
                self.level_max_col = max(self.level_max_col, column)
                self.level_min_col = min(self.level_min_col, column)

    def request(self, command: str) -> None:
        with self.lock:
            self.requested = command

    def note_restart(self) -> None:
        with self.lock:
            self.history.clear()
            self.run_ended = False
            self.reset_count += 1
            self._ended_at = None

    def note_episode_end(self, telemetry: dict) -> None:
        """Record the outcome once per episode, so the viewer can show a running tally."""
        with self.lock:
            if self._ended_at is None:
                self._ended_at = time.monotonic()
                state = telemetry.get("state", {})
                outcome = (
                    "stage_clear"
                    if state.get("stage_clear")
                    else ("death" if state.get("dead") else "ended")
                )
                mark = {
                    "episode": len(self.episodes) + 1,
                    "x": state.get("best_progress") or state.get("x") or 0,
                    "at_x": state.get("x") or 0,
                    "outcome": outcome,
                    "lives_lost": state.get("lives"),
                    "decisions": telemetry.get("decision_index"),
                }
                self.episodes.append(mark)
                # Marks are keyed by x so repeated deaths at one spot stack into a tally,
                # which is what makes "where does it keep dying" readable at a glance.
                if outcome == "stage_clear":
                    self.clear_marks.append(mark)
                    # A clear means Mario reached the flagpole; its x is now known.
                    self.flag_x = mark["at_x"]
                    self.memory.note_clear(mark)
                else:
                    self.death_marks.append(mark)
                    self.memory.note_death(mark)
                self.episodes = self.episodes[-200:]
                self.death_marks = self.death_marks[-200:]
                self.clear_marks = self.clear_marks[-50:]


class V2HubTransport(ScriptedPilotTransport):
    """The harness-v2 reader plus simulated round-trip and a tap on the pilot payload.

    ``_decide`` is overridden so the stand-in judge answers from the published
    ``takeoff_window`` verdicts — the JevHarness division of labour, where the harness
    does the arithmetic and the judge reads conclusions.  Every outgoing request is kept
    verbatim, so a death can be attributed to the exact state the pilot was given.
    """

    _decide = staticmethod(pilot_choose_v2)

    def __init__(self, hub: VizHub) -> None:
        super().__init__()
        self.hub = hub

    def handle_request(self, request):
        if self.hub.latency_ms:
            time.sleep(self.hub.latency_ms / 1000.0)
        response = super().handle_request(request)
        payload = self.requests[-1]
        answer = self.responses[-1]
        state = payload.get("state")
        chosen = (
            answer.get("answers", {}).get("next_action", {}).get("choice")
            if isinstance(answer, dict)
            else None
        )
        with self.hub.lock:
            self.hub.model_input = state
            if isinstance(state, dict):
                self.hub.memory.enabled = self.hub.memory_enabled
                self.hub.memory.observe_request(state)
                if chosen:
                    self.hub.memory.note_choice(str(chosen))
        return response


# ----------------------------------------------------------------------- web "dashboard"
class WebDashboard:
    """Implements the dashboard protocol the runner expects, publishing to the hub.

    ``_run_realtime_dashboard`` calls ``draw`` once per emulator frame and acts on the
    returned command, so pacing lives here: the upstream window uses a 60fps clock and
    the browser feed uses this hub's configured rate.
    """

    def __init__(self, hub: VizHub, env_source: dict | None = None) -> None:
        self.hub = hub
        # `env_source or {}` would be a bug here: the caller passes an empty dict as a live
        # handle and fills it in once the runner builds the env, and an empty dict is
        # falsy, so `or` would silently swap in a different dict that never gets filled.
        self._env_source = env_source if env_source is not None else {}
        self._last_draw = time.monotonic()
        self._last_recorded = None
        self._level_at = 0.0

    @property
    def _env(self):
        return self._env_source.get("env")

    def attach_env(self, env) -> None:
        """The loop hands over the live environment so the level map can be read from it."""
        self._env_source["env"] = env

    def _read_ram(self):
        """Dig the emulator's 2 KB RAM out of however deeply the env is wrapped."""
        node = self._env
        for _ in range(8):
            if node is None:
                return None
            ram = getattr(node, "ram", None)
            if ram is not None:
                return ram
            node = getattr(node, "env", None)
        return None

    def _observe_level(self, snapshot) -> None:
        """Fold the emulator's nametable into the accumulating level map.

        The NES only exposes a 512px window of the level at a time, so a full map of 1-1
        has to be stitched together from many frames.  Reading it every frame would waste
        CPU for no benefit, hence the throttle.
        """
        if self._env is None:
            return
        now = time.monotonic()
        if now - self._level_at < 0.25:
            return
        self._level_at = now

        ram = self._read_ram()
        if ram is None or len(ram) < 0x0500 + 2 * 208:
            return

        # The window base must come from the emulator's own scroll position.  `snapshot.x`
        # alone is wrong by the screen lead, which lands the pages half a screen off.  The
        # game exposes the screen-relative offset the same way gym computes it:
        # `left = (ram[0x86] - ram[0x071c]) % 256`, so `camera = x - left`.  (0x071c holds
        # only the low byte of the camera, which is why reading it alone was wrong.)
        left = (int(ram[0x0086]) - int(ram[0x071C])) % 256
        camera = max(0, int(snapshot.x) - left)
        block = (camera // 512) * 512

        triples: list[tuple[int, int, bool]] = []
        for page in range(2):
            base = 0x0500 + page * 208
            for sub in range(16):
                column = (block + page * 256 + sub * 16) // 16
                for row in range(13):
                    triples.append((column, row, ram[base + row * 16 + sub] != 0))
        self.hub.observe_grid(triples)

    def _pace(self) -> None:
        fps = self.hub.fps
        target = 1.0 / fps if fps > 0 else 0.0
        elapsed = time.monotonic() - self._last_draw
        if elapsed < target:
            time.sleep(target - elapsed)
        self._last_draw = time.monotonic()

    def draw(
        self,
        frame,
        snapshot,
        decision,
        *,
        decision_index: int,
        episode_reward: float,
        waiting: bool = False,
        run_ended: bool = False,
    ) -> DashboardCommand:
        hub = self.hub

        # A paused feed keeps serving the last frame; the loop parks here instead of
        # spinning, and still notices a restart or quit request while parked.
        while hub.paused.is_set() and hub.requested is None:
            time.sleep(0.05)

        self._pace()
        try:
            self._observe_level(snapshot)
        except Exception:  # the map is decorative; never let it break the decision loop
            pass

        telemetry = self._telemetry(
            snapshot, decision, decision_index, episode_reward, waiting, run_ended
        )
        with hub.lock:
            if frame is not None:
                rgb = np.asarray(frame)[:, :, :3]
                hub.height, hub.width = rgb.shape[0], rgb.shape[1]
                alpha = np.full((*rgb.shape[:2], 1), 255, dtype=np.uint8)
                hub.snapshot_rgba = np.concatenate([rgb, alpha], axis=2)
                hub.frame_rgba = hub.snapshot_rgba.tobytes()
            hub.telemetry = telemetry
            hub.run_ended = run_ended
            # `draw` runs once per emulator frame while a decision stays active, so the
            # history is keyed on the decision index to get one point per decision.
            if decision is not None and decision_index != self._last_recorded:
                self._last_recorded = decision_index
                hub.history.append(
                    {
                        "decision": decision_index,
                        "x": snapshot.progress,
                        "best_x": snapshot.best_progress,
                        "action": decision.action.value,
                        "confidence": decision.confidence,
                        "latency_ms": decision.latency_ms,
                        "grounded": snapshot.grounded,
                    }
                )
                hub.history = hub.history[-600:]

            command = DashboardCommand.CONTINUE
            if hub.requested == "restart":
                command = DashboardCommand.RESTART
            elif hub.requested == "quit":
                command = DashboardCommand.QUIT
            hub.requested = None

        # Upstream keeps the dashboard open after death or a clear, waiting for R.  A
        # viewing service should keep playing instead, so once the episode has settled
        # (nothing in flight — the runner only logs a decision when its future resolves)
        # and a short pause has elapsed, ask for a restart through the same command path
        # the Restart button uses.  The pause matters: without it the viewer would never
        # see the death that ended the episode.
        if run_ended and not waiting and command == DashboardCommand.CONTINUE:
            hub.note_episode_end(telemetry)
            if hub.auto_restart and hub._ended_at is not None:
                if time.monotonic() - hub._ended_at >= hub.auto_restart_seconds:
                    with hub.lock:
                        hub.requested = "restart"

        if command == DashboardCommand.RESTART:
            hub.note_restart()
            hub.memory.start_episode()
        return command

    def _telemetry(
        self, snapshot, decision, decision_index, episode_reward, waiting, run_ended
    ) -> dict:
        threat = snapshot.threat_features()
        navigation = snapshot.navigation_features()
        return {
            "decision_index": decision_index,
            "action": decision.action.value if decision else None,
            "action_description": ACTION_DESCRIPTIONS[decision.action] if decision else None,
            "confidence": decision.confidence if decision else None,
            "latency_ms": decision.latency_ms if decision else None,
            "probabilities": dict(decision.probabilities) if decision else {},
            "jump_useful": decision.jump_needed_probability if decision else None,
            "danger": decision.danger_score if decision else None,
            "episode_reward": episode_reward,
            "waiting": waiting,
            "run_ended": run_ended,
            "state": {
                "x": snapshot.x,
                "y": snapshot.y,
                "grounded": snapshot.grounded,
                "direction": snapshot.direction,
                "jump_phase": snapshot.jump_phase,
                "progress": snapshot.progress,
                "best_progress": snapshot.best_progress,
                "stalled": snapshot.stalled_steps,
                "time_left": snapshot.time_left,
                "lives": snapshot.lives,
                "dead": snapshot.dead,
                "stage_clear": snapshot.clear,
                "enemies": [enemy.kind for enemy in snapshot.enemies],
                "grid": list(snapshot.local_grid),
                "terrain": navigation.get("summary"),
                "reaction_horizon_frames": (
                    snapshot.decision_horizon_frames + snapshot.last_response_delay_frames
                ),
                "jump_must_start_this_decision": threat["jump_must_start_this_decision"],
            },
        }

    def save(self, path: Path) -> None:
        """Satisfy the dashboard protocol; the server offers /snapshot.png instead."""
        rgba = self.hub.snapshot_rgba
        if rgba is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(png_bytes(rgba))

    def close(self) -> None:
        with self.hub.lock:
            self.hub.telemetry = {**self.hub.telemetry, "status": "closed"}


# --------------------------------------------------------------------------- the runner
def run_loop(hub: VizHub, *, seed: int) -> None:
    """Drive the real upstream dashboard loop in this thread."""
    created: dict[str, object] = {}
    upstream_factory = runner_module.create_mario_env

    def observed_factory(env_id: str, render_mode: str = "human"):
        env = upstream_factory(env_id, render_mode)
        created["env"] = env
        return env

    runner_module.create_mario_env = observed_factory  # type: ignore[assignment]
    # Sensor fix: the upstream grid reads the nametable with an absolute base, which is
    # wrong whenever floor(camera/256) is odd — the model's hazard view goes blank for
    # ~half of all positions (REPORT §11).  The corrected parser rebuilds the grid from
    # the camera-derived base; everything downstream sees the same snapshot shape.
    runner_module.MarioStateParser = CorrectedParser
    dashboard = WebDashboard(hub, env_source=created)
    hub.memory.start_episode()
    runner_module.LiveDashboard = lambda: dashboard  # type: ignore[assignment]

    transport = V2HubTransport(hub)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # The v2 harness injects prior_attempts (with distilled lessons) itself, so the
    # client patch must NOT also merge memory — double injection would overwrite the
    # lessons with raw deaths.
    with patched_client(transport):
        policy = MarioHarnessV2(memory=hub.memory)
        runner_module.run_episode(
            env_id=hub.env_id,
            policy=policy,
            frames_per_decision=hub.frames_per_decision,
            max_decisions=MAX_DECISIONS,
            seed=seed,
            artifacts_dir=ARTIFACTS,
            display="dashboard",
        )


# --------------------------------------------------------------------------- HTTP layer
PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jev × Mario — 结构化决策闭环</title>
<style>
  :root {
    --canvas:#0f1115; --surface:#16191f; --raised:#1d2128; --line:#303640;
    --text:#eceff3; --muted:#8d96a3; --accent:#89a6c1; --accent-soft:#485969;
    --warning:#d2a764; --danger:#c77065; --ok:#63b06a;
  }
  * { box-sizing: border-box; }
  body {
    margin:0; background:var(--canvas); color:var(--text);
    font:14px/1.5 -apple-system, "Segoe UI", "PingFang SC", "Helvetica Neue", sans-serif;
  }
  code, pre, .mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
  header {
    display:flex; align-items:center; gap:18px; padding:12px 22px;
    border-bottom:1px solid var(--line); background:var(--surface);
    position:sticky; top:0; z-index:5;
  }
  .brand { font-size:17px; font-weight:600; letter-spacing:.2px; }
  .brand .sub { color:var(--muted); font-weight:400; font-size:13px; margin-left:8px; }
  .status { display:flex; align-items:center; gap:8px; color:var(--muted); font-size:13px; }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--accent); }
  .dot.waiting { background:var(--warning); }
  .dot.ended { background:var(--danger); }
  .dot.paused { background:var(--muted); }
  .spacer { flex:1; }
  button, select, a.btn {
    background:var(--raised); color:var(--text); border:1px solid var(--line);
    border-radius:6px; padding:7px 13px; font-size:13px; cursor:pointer;
    text-decoration:none; font-family:inherit;
  }
  button:hover, a.btn:hover { border-color:var(--accent); }
  .toggle { display:flex; align-items:center; gap:6px; color:var(--muted); font-size:13px; cursor:pointer; }
  .toggle input { accent-color: var(--accent); }
  .banner {
    padding:9px 22px; font-size:12.5px; color:var(--warning);
    background:rgba(210,167,100,.09); border-bottom:1px solid var(--line);
  }
  main { display:grid; grid-template-columns: minmax(0,1fr) 460px; gap:20px; padding:20px 22px 40px; }
  @media (max-width:1180px) { main { grid-template-columns: 1fr; } }
  .stage { display:flex; flex-direction:column; gap:14px; min-width:0; }
  .screen {
    background:#000; border:1px solid var(--line); border-radius:8px; overflow:hidden;
    width:fit-content; margin-inline:auto; line-height:0;
  }
  /* The canvas carries the 256:240 intrinsic ratio, so capping its height caps the
     whole stage without distorting the picture or pushing the panels below the fold. */
  canvas#view {
    display:block; image-rendering: pixelated;
    width:auto; height:auto; max-width:100%; max-height:64vh;
  }
  .stats { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; }
  .stat { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:11px 13px; }
  .stat .k { color:var(--muted); font-size:12px; }
  .stat .v { font-size:19px; margin-top:3px; font-variant-numeric: tabular-nums; }
  .panel { display:flex; flex-direction:column; gap:14px; }
  .block { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }
  .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.7px; margin-bottom:9px; }
  .label .hint { text-transform:none; letter-spacing:0; color:var(--accent-soft); }
  .action { font-size:24px; font-weight:600; }
  .desc { color:var(--muted); font-size:12.5px; margin-top:5px; min-height:34px; }
  .metrics { display:grid; grid-template-columns: repeat(3,1fr); gap:10px; margin-top:13px; }
  .metric .k { color:var(--muted); font-size:12px; }
  .metric .v { font-size:16px; margin-top:2px; font-variant-numeric: tabular-nums; }
  .barrow { margin-bottom:9px; }
  .barhead { display:flex; justify-content:space-between; font-size:12.5px; color:var(--muted); }
  .barrow.on .barhead { color:var(--text); }
  .track { height:7px; background:var(--raised); border-radius:4px; margin-top:5px; overflow:hidden; }
  .fill { height:100%; background:var(--accent-soft); border-radius:4px; }
  .barrow.on .fill { background:var(--accent); }
  .fill.danger { background:var(--danger); }
  .fill.warning { background:var(--warning); }
  .kv { display:flex; justify-content:space-between; font-size:13px; padding:3px 0; }
  .kv .k { color:var(--muted); }
  pre.grid {
    margin:0; font-size:13px; line-height:1.35; letter-spacing:2px;
    color:var(--text); background:var(--canvas); border-radius:6px; padding:10px 12px;
    overflow-x:auto;
  }
  pre.json { margin:0; font-size:11.5px; line-height:1.45; color:var(--muted);
             max-height:320px; overflow:auto; background:var(--canvas);
             border-radius:6px; padding:10px 12px; }
  .hintline { color:var(--muted); font-size:12.5px; margin-top:8px; }
  details summary { cursor:pointer; color:var(--muted); font-size:12.5px; }
  .flag { color:var(--danger); font-weight:600; }
  .learning-strip { max-width:1500px; margin:14px auto 0; padding:0 22px; }
  .learning-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin:0 0 9px; }
  .learning-head strong { font-size:14px; }
  .learning-head span, .loop-note { color:var(--muted); font-size:12px; }
  .decision-loop { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:9px; }
  .loop-step { min-width:0; padding:10px 12px; background:var(--surface); border:1px solid var(--line); border-radius:8px; }
  .loop-step .step-no { color:var(--accent); font:11px ui-monospace,monospace; }
  .loop-step strong { display:block; margin:2px 0 3px; font-size:13px; }
  .loop-step span:last-child { display:block; color:var(--muted); font-size:11.5px; line-height:1.45; }
  .loop-note { margin:7px 2px 0; line-height:1.55; }
  .loop-note b { color:var(--warning); font-weight:600; }
  @media (max-width:760px) {
    header { flex-wrap:wrap; gap:9px; padding:10px 14px; }
    header .spacer { display:none; }
    .learning-strip { padding:0 14px; }
    .decision-loop { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .learning-head { display:block; }
    .learning-head span { display:block; margin-top:3px; }
    main { padding:14px; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">Jev × Mario<span class="sub">结构化决策闭环</span></div>
  <div class="status"><span id="dot" class="dot"></span><span id="statusText">连接中…</span></div>
  <div class="spacer"></div>
  <button id="restart">重新开始</button>
  <button id="pause">暂停</button>
  <label class="toggle"><input type="checkbox" id="autorestart" checked> 自动重开</label>
  <select id="speed">
    <option value="12">0.4×（12 帧/秒）</option>
    <option value="30" selected>1×（30 帧/秒）</option>
    <option value="60">2×（60 帧/秒）</option>
    <option value="240">最快（240 帧/秒）</option>
  </select>
  <a class="btn" href="/snapshot.png" download="typesafe-mario.png">保存截图</a>
</header>
<div class="banner">
  当前运行 <b>本地规则 pilot（mock）</b>，不是 Jev。页面中的分布、置信度、Noul 与 Score 均为替身演示值；真实模拟器闭环不等于真实模型评测。
</div>
<section class="learning-strip" aria-label="Mario 结构化决策流程">
  <div class="learning-head">
    <strong>一拍决策的闭环</strong>
    <span>跟着 ①→④ 看一轮，再回到 ① 观察环境反馈</span>
  </div>
  <div class="decision-loop">
    <div class="loop-step"><span class="step-no">01 · OBSERVE</span><strong>读取状态</strong><span>从 NES 内存提取位置、速度、地形和敌人；截图只供人观看。</span></div>
    <div class="loop-step"><span class="step-no">02 · STRUCTURE</span><strong>整理成事实</strong><span>程序推导轨迹、危险窗口与反应时间，组成结构化 state。</span></div>
    <div class="loop-step"><span class="step-no">03 · CHOOSE</span><strong>选择有限动作</strong><span>Choice 在 7 个控制宏中选一个，例如右跑、右跑跳或松开。</span></div>
    <div class="loop-step"><span class="step-no">04 · EXECUTE</span><strong>程序执行并反馈</strong><span>控制器把动作映射为按键并推进若干帧，再读取新状态。</span></div>
  </div>
  <p class="loop-note"><b>读图提示：</b>原始 <code>local_grid</code> 仅作调试可视化，不直接发送给模型；本地 pilot 用于演示数据流，不能据此解读为 Jev 的行为或能力。</p>
</section>
<main>
  <section class="stage">
    <div class="screen"><canvas id="view" width="768" height="720"></canvas></div>
    <div class="stats">
      <div class="stat"><div class="k">决策序号</div><div class="v" id="sIdx">—</div></div>
      <div class="stat"><div class="k">当前进度 x</div><div class="v" id="sX">—</div></div>
      <div class="stat"><div class="k">本局最远</div><div class="v" id="sBest">—</div></div>
      <div class="stat"><div class="k">战绩</div><div class="v" id="sRecord">—</div></div>
    </div>
    <div class="block">
      <div class="label">关卡地图 <span class="hint">· 实线为已探明地形，虚线为尚未走到</span></div>
      <canvas id="map" width="1400" height="260" style="width:100%;height:auto"></canvas>
      <div class="hintline" id="mapHint"></div>
    </div>

    <div class="block">
      <div class="label">阵亡分布 <span class="hint">· 每格代表一段关卡，颜色越深死得越多</span></div>
      <canvas id="deaths" width="1400" height="90" style="width:100%;height:auto"></canvas>
      <div class="hintline" id="deathHint"></div>
    </div>

    <div class="block">
      <div class="label">进度曲线 <span class="hint">· 每次决策一个点，蓝色为落地决策</span></div>
      <canvas id="spark" width="900" height="120" style="width:100%;height:120px"></canvas>
    </div>
  </section>

  <aside class="panel">
    <div class="block">
      <div class="label">本地 pilot 的 Choice 示意输出 <span class="hint">· mock，不是 Jev</span></div>
      <div class="action" id="actionName">等待首个决策…</div>
      <div class="desc" id="actionDesc"></div>
      <div class="metrics">
        <div class="metric"><div class="k">示意置信度</div><div class="v" id="mConf">—</div></div>
        <div class="metric"><div class="k">模拟往返延迟</div><div class="v" id="mLat">—</div></div>
        <div class="metric"><div class="k">累计回报</div><div class="v" id="mRew">—</div></div>
      </div>
    </div>

    <div class="block">
      <div class="label">七个动作的示意分布 <span class="hint">· mock 值</span></div>
      <div id="bars"></div>
    </div>

    <div class="block">
      <div class="label">辅助判断示意 <span class="hint">· mock Noul / Score</span></div>
      <div id="situation"></div>
    </div>

    <div class="block">
      <div class="label">调试视图：原始碰撞网格 <span class="hint">local_grid · 未发送给模型</span></div>
      <pre class="grid" id="grid">—</pre>
      <div class="hintline" id="terrain"></div>
    </div>

    <div class="block">
      <div class="label">游戏状态</div>
      <div id="gamestate"></div>
    </div>

    <div class="block">
      <div class="label">本地扩展：跨局尝试记忆
        <span class="hint">· 不属于上游默认策略</span></div>
      <label class="toggle" style="margin-bottom:8px">
        <input type="checkbox" id="memtoggle" checked> 启用本地记忆扩展
      </label>
      <div id="memlist"></div>
      <button id="forget" style="margin-top:9px">清空记忆</button>
      <div class="hintline" id="memhint"></div>
    </div>

    <details class="block">
      <summary>发给本地 pilot 的结构化 state（点击展开）</summary>
      <pre class="json" id="modelInput" style="margin-top:10px">—</pre>
    </details>
  </aside>
</main>

<script>
const VIEW = document.getElementById('view');
const vctx = VIEW.getContext('2d');
const off = document.createElement('canvas');
const octx = off.getContext('2d');
let dims = {w: 0, h: 0};
let serverPaused = false;
let inFlight = false;

async function pumpFrame() {
  if (!inFlight && dims.w) {
    inFlight = true;
    try {
      const res = await fetch('/frame.rgba', {cache: 'no-store'});
      if (res.ok) {
        const buf = await res.arrayBuffer();
        if (buf.byteLength === dims.w * dims.h * 4) {
          octx.putImageData(new ImageData(new Uint8ClampedArray(buf), dims.w, dims.h), 0, 0);
          vctx.imageSmoothingEnabled = false;
          vctx.drawImage(off, 0, 0, VIEW.width, VIEW.height);
        }
      }
    } catch (e) { /* server restarting; the next tick retries */ }
    inFlight = false;
  }
  setTimeout(pumpFrame, 30);
}

const pct = v => (v === null || v === undefined) ? '—' : (v * 100).toFixed(1) + '%';
const num = (v, d = 0) => (v === null || v === undefined) ? '—' : Number(v).toFixed(d);

function barRow(label, value, opts = {}) {
  const v = Math.max(0, Math.min(1, value || 0));
  const cls = opts.danger ? 'danger' : (opts.warning ? 'warning' : '');
  return `<div class="barrow ${opts.on ? 'on' : ''}">
    <div class="barhead"><span>${label}</span><span>${(v * 100).toFixed(1)}%</span></div>
    <div class="track"><div class="fill ${cls}" style="width:${(v * 100).toFixed(1)}%"></div></div>
  </div>`;
}

function kv(k, v) { return `<div class="kv"><span class="k">${k}</span><span>${v}</span></div>`; }

let sparkData = [];

// ------------------------------------------------ level map (accumulated across runs)
function drawLevelMap(level, cur) {
  const c = document.getElementById('map');
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#0f1115';
  ctx.fillRect(0, 0, c.width, c.height);

  const tiles = level.tiles || {};
  const minCol = level.min_col || 0;
  const maxCol = Math.max(level.max_col || 0, minCol + 8);
  const cols = maxCol - minCol + 1;
  const rows = level.rows || 13;
  const pad = 8;
  const tw = (c.width - pad * 2) / cols;
  const th = (c.height - pad * 2 - 16) / rows;
  const X = col => pad + (col - minCol) * tw;
  const Y = row => pad + 16 + row * th;

  for (const [colStr, rowList] of Object.entries(tiles)) {
    const col = Number(colStr);
    for (const row of rowList) {
      if (row >= rows) continue;
      ctx.fillStyle = row >= 8 ? '#c66c3c' : '#4cbe50';
      ctx.fillRect(X(col), Y(row), Math.max(1, tw - 0.5), Math.max(1, th - 0.5));
    }
  }

  // Deaths stack at the same x; the taller the bar, the more deaths there.
  const byX = {};
  (level.deaths || []).forEach(d => { const k = Math.round(d.at_x / 16); byX[k] = (byX[k] || 0) + 1; });
  const maxDeaths = Math.max(1, ...Object.values(byX));
  for (const [colStr, n] of Object.entries(byX)) {
    const col = Number(colStr);
    const h = 8 + 46 * (n / maxDeaths);
    ctx.fillStyle = `rgba(199,112,101,${0.45 + 0.55 * (n / maxDeaths)})`;
    ctx.fillRect(X(col) - tw * 0.4, Y(0) - 2 - h, Math.max(2, tw * 0.8), h);
    if (n > 1) {
      ctx.fillStyle = '#eceff3';
      ctx.font = 'bold 11px ui-monospace, monospace';
      ctx.fillText(String(n), X(col) - 3, Y(0) - 6 - h);
    }
  }
  for (const clr of (level.clears || [])) {
    const col = Math.round(clr.at_x / 16);
    ctx.fillStyle = '#63b06a';
    ctx.beginPath();
    ctx.arc(X(col), Y(0) - 6, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  if (level.flag_x) {
    const fc = Math.round(level.flag_x / 16);
    ctx.fillStyle = '#63b06a';
    ctx.fillRect(X(fc) - 1, Y(1), 2, (rows - 1) * th);
    ctx.font = '10px ui-monospace, monospace';
    ctx.fillText('旗杆', X(fc) - 14, Y(1) - 2);
  }

  if (cur) {
    const col = Math.round(cur.x / 16);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(X(col) - 1, Y(0) - 3, 2.5, (rows * th) + 6);
    ctx.fillStyle = '#89a6c1';
    ctx.font = '11px ui-monospace, monospace';
    ctx.fillText('现在', X(col) - 12, Y(rows) + 13);
  }
}

function drawDeathHistogram(level) {
  const c = document.getElementById('deaths');
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#0f1115';
  ctx.fillRect(0, 0, c.width, c.height);

  const deaths = level.deaths || [];
  const buckets = 56;
  const counts = new Array(buckets).fill(0);
  const maxX = Math.max(2000, ...deaths.map(d => d.at_x || 0));
  deaths.forEach(d => {
    const b = Math.min(buckets - 1, Math.floor(((d.at_x || 0) / maxX) * buckets));
    counts[b] += 1;
  });
  const peak = Math.max(1, ...counts);
  const pad = 8;
  const bw = (c.width - pad * 2) / buckets;
  const usable = c.height - pad * 2 - 14;
  counts.forEach((n, i) => {
    const h = n ? Math.max(4, usable * (n / peak)) : 0;
    ctx.fillStyle = n ? `rgba(199,112,101,${0.35 + 0.65 * (n / peak)})` : '#1d2128';
    ctx.fillRect(pad + i * bw, pad + usable - h, Math.max(1, bw - 1.5), h || 2);
  });
  ctx.fillStyle = '#8d96a3';
  ctx.font = '11px ui-monospace, monospace';
  ctx.fillText('x=0', pad, c.height - 4);
  ctx.fillText('x=' + maxX, c.width - pad - String(maxX).length * 7, c.height - 4);
  if (deaths.length) {
    const worst = counts.indexOf(peak);
    const wx = Math.round((worst + 0.5) * (maxX / buckets));
    document.getElementById('deathHint').textContent =
      `共 ${deaths.length} 次阵亡；最集中的位置 x≈${wx}（${peak} 次）`;
  } else {
    document.getElementById('deathHint').textContent = '还没有阵亡记录';
  }
}

function drawSpark() {
  const c = document.getElementById('spark');
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#0f1115';
  ctx.fillRect(0, 0, c.width, c.height);
  const pad = 14;
  // The real 1-1 flagpole x is only known once a run actually clears the level, so the
  // scale follows the observed flag rather than a hardcoded constant.
  const maxX = window.__flagX ? Math.round(window.__flagX * 1.06) : 3000;
  const Y = x => pad + (c.height - pad * 2) * (1 - Math.min(1, x / maxX));

  if (window.__flagX) {
    const fy = Y(window.__flagX);
    ctx.strokeStyle = '#c77065';
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(pad, fy);
    ctx.lineTo(c.width - pad, fy);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#c77065';
    ctx.font = '11px ui-monospace, monospace';
    ctx.fillText('旗杆 ' + window.__flagX, pad + 4, fy - 4);
  } else {
    ctx.fillStyle = '#485969';
    ctx.font = '11px ui-monospace, monospace';
    ctx.fillText('旗杆位置尚未探明（首次通关后自动标注）', pad, c.height - 4);
  }
  if (!sparkData.length) return;
  const X = i => pad + (c.width - pad * 2) * (i / Math.max(1, sparkData.length - 1));
  ctx.strokeStyle = '#485969';
  ctx.lineWidth = 2;
  ctx.beginPath();
  sparkData.forEach((d, i) => { i ? ctx.lineTo(X(i), Y(d.best_x)) : ctx.moveTo(X(i), Y(d.best_x)); });
  ctx.stroke();
  sparkData.forEach((d, i) => {
    ctx.fillStyle = d.grounded ? '#89a6c1' : '#d2a764';
    ctx.beginPath();
    ctx.arc(X(i), Y(d.x), d.grounded ? 3.4 : 2.2, 0, Math.PI * 2);
    ctx.fill();
  });
}

async function tick() {
  try {
    const s = await (await fetch('/state.json', {cache: 'no-store'})).json();
    if (s.frame) { dims = {w: s.frame.width, h: s.frame.height}; off.width = dims.w; off.height = dims.h; }

    const dot = document.getElementById('dot');
    const statusText = document.getElementById('statusText');
    // The server owns the pause state, so a pause issued through the API shows up here
    // too, not only one made by clicking the button.
    serverPaused = !!s.paused;
    document.getElementById('pause').textContent = serverPaused ? '继续' : '暂停';
    dot.className = 'dot';
    if (serverPaused) { dot.classList.add('paused'); statusText.textContent = '已暂停'; }
    else if (s.run_ended) {
      dot.classList.add('ended');
      const secs = s.restart_in;
      const what = s.state.stage_clear ? '通关' : '本局结束';
      statusText.textContent = (s.auto_restart && secs !== null)
        ? `${what}，${secs}s 后重开` : `${what}（可重新开始）`;
    }
    else if (s.waiting) { dot.classList.add('waiting'); statusText.textContent = '等待本地 pilot…'; }
    else { statusText.textContent = '决策循环运行中'; }

    document.getElementById('sIdx').textContent = s.decision_index ?? '—';
    document.getElementById('sX').textContent = s.state.x;
    document.getElementById('sBest').textContent = s.state.best_progress;
    const eps = s.episodes || [];
    const clears = eps.filter(e => e.outcome === 'stage_clear').length;
    document.getElementById('sRecord').innerHTML = eps.length
      ? `${eps.length} 局 · 通关 <span style="color:var(--ok)">${clears}</span>`
      : '第 1 局';

    document.getElementById('actionName').textContent = s.action ? s.action.replace(/_/g, ' ') : '读取状态…';
    document.getElementById('actionDesc').textContent = s.action_description || '';
    document.getElementById('mConf').textContent = pct(s.confidence);
    document.getElementById('mLat').textContent = s.latency_ms === null ? '—' : num(s.latency_ms) + ' ms';
    document.getElementById('mRew').textContent = (s.episode_reward >= 0 ? '+' : '') + num(s.episode_reward, 1);

    const order = ['noop','right','right_jump','right_run','right_run_jump','jump','left'];
    document.getElementById('bars').innerHTML = order.map(a =>
      barRow(a.replace(/_/g, ' '), s.probabilities[a] || 0, {on: a === s.action})).join('');

    const jump = s.jump_useful, danger = s.danger === null ? 0 : Math.min(1, s.danger / 2);
    document.getElementById('situation').innerHTML =
      barRow('此刻前跳是否有利', jump) +
      barRow('即时危险度', danger, {danger: danger >= 0.66, warning: danger < 0.66}) +
      kv('反应地平线', s.state.reaction_horizon_frames + ' 帧') +
      kv('必须本次起跳', s.state.jump_must_start_this_decision
          ? '<span class="flag">是</span>' : '否');

    document.getElementById('grid').textContent = (s.state.grid || []).join('\\n') || '—';
    document.getElementById('terrain').textContent = s.state.terrain || '';

    document.getElementById('gamestate').innerHTML =
      kv('位置', s.state.x + ', ' + s.state.y) +
      kv('朝向 / 跳跃阶段', s.state.direction.replace(/_/g, ' ') + ' · ' + s.state.jump_phase) +
      kv('着地', s.state.grounded ? '是' : '否') +
      kv('附近敌人', s.state.enemies.length ? s.state.enemies.join(', ') : '无') +
      kv('卡住帧数', s.state.stalled) +
      kv('剩余时间 / 生命', s.state.time_left + ' · ' + s.state.lives) +
      kv('旗杆 960', s.state.stage_clear
          ? '<span class="flag">已到达 ✓</span>' : '未到达') +
      kv('当前策略', s.model_proxy ? '规则 pilot（mock）' : '—');

    const mi = await (await fetch('/model_input.json', {cache: 'no-store'})).json();
    document.getElementById('modelInput').textContent = mi.state
      ? JSON.stringify(mi.state, null, 2) : '（等待首个请求）';

    const h = await (await fetch('/history.json', {cache: 'no-store'})).json();
    sparkData = h.history || [];
    drawSpark();

    renderMemory(s);

    const lvl = await (await fetch('/level.json', {cache: 'no-store'})).json();
    window.__flagX = s.flag_x || lvl.flag_x || null;
    drawLevelMap(lvl, s.state);
    drawDeathHistogram(lvl);
    drawSpark();
    const known = Object.keys(lvl.tiles || {}).length;
    document.getElementById('mapHint').textContent =
      `已探明 ${known} 个瓦片列（x 约 ${(lvl.min_col || 0) * 16} – ${(lvl.max_col || 0) * 16}）`
      + ` · 死亡 ${(lvl.deaths || []).length} 次 · 通关 ${(lvl.clears || []).length} 次`;
  } catch (e) { /* retry on next tick */ }
  setTimeout(tick, 220);
}

document.getElementById('restart').onclick = () => fetch('/control', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({command: 'restart'})
});
document.getElementById('pause').onclick = () => fetch('/control', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({command: serverPaused ? 'resume' : 'pause'})
});
document.getElementById('speed').onchange = e => fetch('/control', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({command: 'speed', fps: Number(e.target.value)})
});
function renderMemory(s) {
  const box = document.getElementById('memlist');
  const recs = s.death_records || [];
  document.getElementById('memtoggle').checked = !!s.memory_enabled;
  if (!recs.length) {
    box.innerHTML = '<div class="hintline" style="margin:0">还没有阵亡记录，记忆为空。</div>';
  } else {
    const rows = [...recs].reverse();
    box.innerHTML = rows.map((d, i) => {
      const trace = (d.final_decisions || []).map(t =>
        `<span class="mono">x${t.x}/${(t.action||'').replace(/_/g,'')}${t.airborne?'✈':''}</span>`
      ).join(' ');
      return `<div style="border-left:2px solid var(--danger);padding:4px 0 6px 9px;margin-bottom:7px">
        <div style="font-size:13px">阵亡于 <b>x=${d.at_x}</b> · ${d.action_when_lost || '—'}</div>
        <div class="hintline" style="margin:2px 0">${d.cause}</div>
        <div class="hintline mono" style="font-size:11px;margin:0">${trace}</div>
      </div>`;
    }).join('');
  }
  document.getElementById('memhint').textContent = s.memory_enabled
    ? `已尝试 ${s.attempts || 0} 局；最近 ${recs.length} 次阵亡会注入本地扩展 state`
    : '记忆已关闭：请求里不含 prior_attempts';
}
document.getElementById('memtoggle').onchange = e => fetch('/control', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({command: 'memory', enabled: e.target.checked})
});
document.getElementById('forget').onclick = () => fetch('/control', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({command: 'forget'})
});
document.getElementById('autorestart').onchange = e => fetch('/control', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({command: 'auto_restart', enabled: e.target.checked})
});

pumpFrame();
tick();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hub: VizHub

    def log_message(self, fmt, *args):  # keep the console readable
        pass

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload) -> None:
        self._send(200, "application/json; charset=utf-8", json.dumps(payload).encode())

    def do_GET(self) -> None:
        hub = self.hub
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode())
        elif path == "/frame.rgba":
            with hub.lock:
                data = hub.frame_rgba
            if data is None:
                self._send(204, "application/octet-stream", b"")
            else:
                self._send(200, "application/octet-stream", data)
        elif path == "/snapshot.png":
            with hub.lock:
                rgba = None if hub.snapshot_rgba is None else hub.snapshot_rgba.copy()
            if rgba is None:
                self._send(204, "image/png", b"")
            else:
                self._send(200, "image/png", png_bytes(rgba))
        elif path == "/state.json":
            with hub.lock:
                payload = {
                    **hub.telemetry,
                    "frame": {"width": hub.width, "height": hub.height},
                    "fps": hub.fps,
                    "simulated_latency_ms": hub.latency_ms,
                    "paused": hub.paused.is_set(),
                    "reset_count": hub.reset_count,
                    "uptime_s": round(time.time() - hub.started_at, 1),
                    "model_proxy": True,
                    "env_kind": hub.env_kind,
                    "flag_x": hub.flag_x,
                    "memory_enabled": hub.memory_enabled,
                    "attempts": hub.memory.episodes,
                    "death_records": [d.to_context() for d in hub.memory.deaths],
                    "env_id": hub.env_id,
                    "auto_restart": hub.auto_restart,
                    "episodes": list(hub.episodes),
                    "seconds_since_end": (
                        None
                        if hub._ended_at is None
                        else round(time.monotonic() - hub._ended_at, 1)
                    ),
                    "restart_in": (
                        None
                        if not hub.auto_restart or hub._ended_at is None
                        else round(
                            max(0.0, hub.auto_restart_seconds - (time.monotonic() - hub._ended_at)),
                            1,
                        )
                    ),
                }
            self._json(payload)
        elif path == "/level.json":
            with hub.lock:
                tiles = {
                    str(column): sorted(row for row, solid in rows.items() if solid)
                    for column, rows in hub.level_tiles.items()
                }
                payload = {
                    "tiles": tiles,
                    "min_col": hub.level_min_col,
                    "max_col": hub.level_max_col,
                    "rows": 13,
                    "deaths": list(hub.death_marks),
                    "clears": list(hub.clear_marks),
                    "flag_x": hub.flag_x,
                    "memory_enabled": hub.memory_enabled,
                    "attempts": hub.memory.episodes,
                    "death_records": [d.to_context() for d in hub.memory.deaths],
                }
            self._json(payload)
        elif path == "/model_input.json":
            with hub.lock:
                payload = {"state": hub.model_input}
            self._json(payload)
        elif path == "/history.json":
            with hub.lock:
                payload = {
                    "history": list(hub.history),
                    "flag_x": hub.flag_x,
                    "memory_enabled": hub.memory_enabled,
                    "attempts": hub.memory.episodes,
                    "death_records": [d.to_context() for d in hub.memory.deaths],
                    "reset_count": hub.reset_count,
                }
            self._json(payload)
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self) -> None:
        hub = self.hub
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}

        command = body.get("command")
        if self.path.split("?", 1)[0] != "/control" or not command:
            self._send(400, "application/json", b'{"ok":false}')
            return

        if command == "pause":
            hub.paused.set()
        elif command == "resume":
            hub.paused.clear()
        elif command in ("restart", "quit"):
            hub.request(command)
        elif command == "memory":
            with hub.lock:
                hub.memory_enabled = bool(body.get("enabled"))
                hub.memory.enabled = hub.memory_enabled
        elif command == "forget":
            with hub.lock:
                hub.memory.deaths.clear()
                hub.memory.clears.clear()
                hub.death_marks.clear()
                hub.clear_marks.clear()
                hub.memory.episodes = 0
        elif command == "auto_restart":
            with hub.lock:
                hub.auto_restart = bool(body.get("enabled"))
                if hub.auto_restart and hub._ended_at is not None:
                    hub._ended_at = time.monotonic() - hub.auto_restart_seconds
        elif command == "speed":
            fps = float(body.get("fps") or hub.fps)
            with hub.lock:
                hub.fps = max(1.0, min(600.0, fps))
        else:
            self._send(400, "application/json", b'{"ok":false}')
            return

        self._json(
            {
                "ok": True,
                "command": command,
                "fps": hub.fps,
                "auto_restart": hub.auto_restart,
                "memory_enabled": hub.memory_enabled,
            }
        )


def lan_addresses() -> list[str]:
    """Best-effort list of this host's reachable non-loopback IPv4 addresses.

    Ordering matters: a machine commonly carries virtual interfaces (VPN tunnels, Docker,
    the 198.18.0.0/15 benchmark range some proxies use) whose addresses are not reachable
    from another device on the LAN.  Real private ranges are listed first so the banner
    shows the address a phone or colleague can actually open.
    """
    found: list[str] = []
    try:
        import socket

        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in found and not address.startswith("127."):
                found.append(address)
        # A UDP socket to a public address reports the interface that would route out,
        # which covers hosts whose own hostname does not resolve to the LAN address.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if address not in found and not address.startswith("127."):
                found.insert(0, address)
    except OSError:
        pass
    return sorted(found, key=lan_address_rank)


def lan_address_rank(address: str) -> tuple[int, str]:
    """Sort key: home/office LAN ranges first, link-local and benchmark ranges last."""
    octets = address.split(".")
    if len(octets) != 4:
        return (3, address)
    try:
        first, second = int(octets[0]), int(octets[1])
    except ValueError:
        return (3, address)
    if first == 192 and second == 168:
        return (0, address)  # the common case
    if first == 10 or (first == 172 and 16 <= second <= 31):
        return (1, address)  # other private ranges
    if first == 169 and second == 254:
        return (3, address)  # link-local, self-assigned
    if first == 198 and second in (18, 19):
        return (3, address)  # benchmarking range, often a virtual adapter
    return (2, address)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address; 0.0.0.0 exposes the viewer to the whole network",
    )
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--fps", type=float, default=30.0, help="emulator frames per second")
    parser.add_argument(
        "--latency-ms",
        type=float,
        default=60.0,
        help="simulated mock-pilot wait, so reaction_timing is non-trivial",
    )
    parser.add_argument("--frames-per-decision", type=int, default=8)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    hub = VizHub(
        fps=args.fps,
        latency_ms=args.latency_ms,
        frames_per_decision=args.frames_per_decision,
    )
    Handler.hub = hub

    thread = threading.Thread(
        target=run_loop, args=(hub,), kwargs={"seed": args.seed}, daemon=True
    )
    thread.start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True

    local_url = f"http://127.0.0.1:{args.port}/"
    exposed = args.host in ("0.0.0.0", "::", "")

    print("typesafe-mario 可视化服务")
    print(f"  绑定地址   {args.host}:{args.port}")
    print(f"  本机访问   {local_url}")
    if exposed:
        addresses = lan_addresses()
        if addresses:
            for address in addresses:
                print(f"  局域网访问 http://{address}:{args.port}/")
        else:
            print(f"  局域网访问 http://<本机IP>:{args.port}/")
        print("  ⚠️  已监听所有网络接口：同一网络内的任何设备都能访问，且该服务没有认证。")
        print("     仅在可信网络（如自己的局域网）使用；避免在公共网络或直接暴露到公网。")
    print(f"  模拟器     真实 gym_super_mario_bros + 内置 NES ROM（{args.frames_per_decision} 帧/决策）")
    print(f"  策略应答   本地 scripted pilot（mock，非 Jev），模拟等待 {args.latency_ms:.0f}ms")
    print(f"  画面速率   {args.fps:.0f} 帧/秒（网页上可调）")
    print("  按 Ctrl+C 结束")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(local_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
