"""Camera-corrected parser: fixes the nametable page selection for the live emulator.

The bug
-------
Upstream ``MarioStateParser._extract_local_grid`` samples the 2 KB RAM tile buffer at
0x0500 using the *absolute* level x::

    page  = (sample_x // 256) % 2
    sub_x = (sample_x % 256) // 16

That is correct only if the two 16x13 nametable pages are aligned to even 256px
boundaries of the level.  On the real emulator they are not: the game scrolls the pair of
pages along with the camera, so the buffer covers the level window

    [256 * floor(camera / 256), 256 * floor(camera / 256) + 512)

Whenever ``floor(camera / 256)`` is **odd**, the upstream page choice is off by exactly
one page (256px).  Measured consequence (see REPORT §11): with Mario at x=1094 the
upstream grid is *completely empty* — no pit, no ground, no pipe — while the
camera-derived grid shows the terrain.  Half the time the model's only hazard sensor is
blind, which is why episodes kept dying at the same pits: the model was told the path
was clear.

The fix here
------------
``CorrectedParser`` subclasses the upstream parser and, after the normal parse, rebuilds
the 11x9 grid from the same RAM with the camera-derived base and patches it into the
frozen snapshot. Every derived terrain fact published in the state (``terrain.obstacle_ahead``,
``gap_distance_tiles``, the local grid itself) is recomputed from the corrected grid,
because the upstream snapshot derives them from ``local_grid`` lazily.  Nothing upstream
is modified; the wrapper is injected wherever our scripts construct the runner.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from typesafe_mario.state import MarioStateParser

GRID_COLS = 11
GRID_ROWS = 9
X_OFFSETS = range(-2, 9)
Y_OFFSETS = range(-4, 5)
NAMETABLE_BASE = 0x0500
NAMETABLE_PAGE_BYTES = 208
SCREEN_TOP = 32


def camera_x_from_ram(ram: Any, mario_x: int) -> int:
    """Scroll position of the screen's left edge, the way nes-py itself computes it."""
    left = (int(ram[0x0086]) - int(ram[0x071C])) % 256
    return max(0, mario_x - left)


def build_grid(ram: Any, mario_x: int, mario_y: int) -> list[str]:
    """The 11x9 collision window, sampled with the camera-derived nametable base."""
    base = 256 * (camera_x_from_ram(ram, mario_x) // 256)
    rows: list[str] = []
    for dy_tiles in Y_OFFSETS:
        line = ""
        for dx_tiles in X_OFFSETS:
            sample_x = mario_x + dx_tiles * 16
            sample_y = mario_y + dy_tiles * 16
            page = (sample_x - base) // 256
            sub_x = ((sample_x - base) % 256) // 16
            sub_y = (sample_y - SCREEN_TOP) // 16
            solid = (
                0 <= page <= 1
                and 0 <= sub_y < 13
                and ram[NAMETABLE_BASE + page * NAMETABLE_PAGE_BYTES + sub_y * 16 + sub_x]
            )
            line += "#" if solid else "."
        rows.append(line)
    # Mario's marker sits at (col 2, row 4), exactly as upstream places it.
    lines = []
    for row_index, line in enumerate(rows):
        if row_index == 4:
            line = line[:2] + "M" + line[3:]
        lines.append(line)
    return lines


class CorrectedParser(MarioStateParser):
    """Drop-in parser replacement: corrects the grid whenever the pages are misaligned."""

    def parse(self, info: dict[str, Any], ram: Any = None, **kwargs: Any):
        snapshot = super().parse(info, ram, **kwargs)
        if ram is None or len(ram) < NAMETABLE_BASE + 2 * NAMETABLE_PAGE_BYTES:
            return snapshot
        try:
            grid = build_grid(ram, int(snapshot.x), int(snapshot.y))
        except Exception:
            return snapshot  # never break the loop over a sensor correction
        if grid == list(snapshot.local_grid):
            return snapshot
        return replace(snapshot, local_grid=tuple(grid))
