from __future__ import annotations
from typing import TYPE_CHECKING
import math

from pywm import PYWM_PRESSED

from .overlay import Overlay
from ..config import configured_value

if TYPE_CHECKING:
    from ..layout import Layout

conf_anim_t = configured_value('anim_time', .3)

MOVES = {
    'h': (-1, 0), 'Left': (-1, 0),
    'l': (1, 0), 'Right': (1, 0),
    'k': (0, -1), 'Up': (0, -1),
    'j': (0, 1), 'Down': (0, 1),
}
CONFIRM = ('Return', 'KP_Enter', 'space')
# Escape, or pressing the Super+A binding again, cancels
CANCEL = ('Escape', 'a')


class PreselectOverlay(Overlay):
    """
    Pick the free tile where the next new window opens: hjkl/arrows jump to the next free tile, mouse hovers free tiles,
    Return/Space/click confirm, Escape or A clears the preselection.
    """
    def __init__(self, layout: Layout) -> None:
        super().__init__(layout)
        self.workspace = layout.get_active_workspace()

        if layout.preselect is not None and layout.preselect[0] == self.workspace._handle:
            _, i, j = layout.preselect
        else:
            layout.preselect = None
            ws_state = layout.state.get_workspace_state(self.workspace)
            i, j = layout.place_initial(self.workspace, ws_state, 1, 1)
        self._set(i, j)

    def _set(self, i: int, j: int) -> None:
        self.layout.preselect = (self.workspace._handle, i, j)

        # Pan so the square stays on screen
        ws_state = self.layout.state.get_workspace_state(self.workspace)
        size = round(ws_state.size)
        vi = min(max(ws_state.i, i - size + 1), i)
        vj = min(max(ws_state.j, j - size + 1), j)
        if (vi, vj) != (ws_state.i, ws_state.j):
            # animate the pan like any other viewport move (overlay_safe: we are inside the overlay)
            new_state = self.layout.state.replacing_workspace_state(self.workspace, i=vi, j=vj)
            self.layout.animate_to(lambda _: (None, new_state), conf_anim_t(), overlay_safe=True)
        else:
            self.layout.damage()

    def _free(self, i: int, j: int) -> bool:
        return self.layout.state.get_workspace_state(self.workspace).is_tile_free(i, j)

    def _tile_under_cursor(self) -> tuple[int, int]:
        ws = self.workspace
        ws_state = self.layout.state.get_workspace_state(ws)
        x, y = self.layout.cursor_pos
        h = ws.height - ws_state.top_excluded - ws_state.bottom_excluded
        i = ws_state.i + (x - ws.pos_x) * ws_state.size / ws.width
        j = ws_state.j + (y - ws.pos_y - ws_state.top_excluded) * ws_state.size / h
        return math.floor(i), math.floor(j)

    def on_key(self, time_msec: int, keycode: int, state: int, keysyms: str) -> bool:
        if state != PYWM_PRESSED:
            return True
        if keysyms in MOVES:
            _, i, j = self.layout.preselect  # type: ignore
            di, dj = MOVES[keysyms]
            for step in range(1, 50):
                if self._free(i + step * di, j + step * dj):
                    self._set(i + step * di, j + step * dj)
                    break
        elif keysyms in CONFIRM:
            self.layout.exit_overlay()
        elif keysyms in CANCEL:
            self.layout.preselect = None
            self.layout.damage()
            self.layout.exit_overlay()
        return True

    def on_motion(self, time_msec: int, delta_x: float, delta_y: float) -> bool:
        i, j = self._tile_under_cursor()
        if self._free(i, j) and self.layout.preselect != (self.workspace._handle, i, j):
            self.layout.preselect = (self.workspace._handle, i, j)
            self.layout.damage()
        return False

    def on_button(self, time_msec: int, button: int, state: int) -> bool:
        if state == PYWM_PRESSED:
            i, j = self._tile_under_cursor()
            if self._free(i, j):
                self.layout.preselect = (self.workspace._handle, i, j)
                self.layout.damage()
                self.layout.exit_overlay()
        return True
