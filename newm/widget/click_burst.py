from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..layout import Layout

import time

from pywm import PyWMWidget, PyWMWidgetDownstreamState, PyWMOutput

from ..config import configured_value

conf_enabled = configured_value('click_burst.enabled', False)
# 'cycles': light cycles (tron_cb_cycles); 'hex': hex code readout (tron_cb_hex); 'ring': shockwave ring (tron_cb_ring);
# 'lock': corner-bracket target lock (tron_cb_lock)
conf_style = configured_value('click_burst.style', 'cycles')


class ClickBurst(PyWMWidget):
    """
    Effect at the pointer on a button press, cyan (orange for the right
    button), one of (click_burst.style):
      ring  shockwave: a hot ring expands from the pointer and fades
      lock  target lock: four corner brackets snap in, flicker, hold, derez
    One per output; hidden (opacity 0, not drawn) between bursts.
    """
    STYLES = {'cycles': ('tron_cb_cycles', 120., 0.25), 'hex': ('tron_cb_hex', 160., 0.4), 'ring': ('tron_cb_ring', 120., 0.4), 'lock': ('tron_cb_lock', 170., 0.55)}
    CY = (0.133, 0.827, 0.933)
    OR = (0.976, 0.451, 0.086)
    BTN_RIGHT = 0x111

    def __init__(self, wm: Layout, output: PyWMOutput, *args: Any, **kwargs: Any):
        self._output = output
        PyWMWidget.__init__(self, wm, output, *args, **kwargs)
        self._box: tuple[float, float, float, float] = (output.pos[0], output.pos[1], 1., 1.)
        self._end: float = 0.

    def burst(self, x: float, y: float, button: int = 0) -> None:
        ox, oy = self._output.pos
        if not (ox <= x < ox + self._output.width and oy <= y < oy + self._output.height):
            return
        shader, size, duration = self.STYLES.get(conf_style(), self.STYLES['cycles'])
        h = size / 2
        self._box = (x - h, y - h, size, size)
        now = time.monotonic()
        self._end = now + duration
        col = self.OR if button == self.BTN_RIGHT else self.CY
        self.set_primitive(shader, [], [now % 3600., self._output.scale, *col])
        self.damage()

    def process(self) -> PyWMWidgetDownstreamState:
        active = time.monotonic() < self._end
        if active:
            # come back once it is over to hide again
            self.damage()
        return PyWMWidgetDownstreamState(1000000, self._box, lock_enabled=True, opacity=1. if active else 0.)
