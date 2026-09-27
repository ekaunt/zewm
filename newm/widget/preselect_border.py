from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..layout import Layout

from pywm import PyWMWidget, PyWMWidgetDownstreamState, PyWMOutput

from ..config import configured_value
from ..util import get_border_color

conf_color = configured_value('preselect.color', '#ff0000')
conf_width = configured_value('preselect.width', 3)
conf_view_corner_radius = configured_value('view.corner_radius', 12)
conf_padding = configured_value('view.padding', 6)


class PreselectBorder(PyWMWidget):
    """
    Outline of where a dragged window will land (Layout.drop_hint), else of the tile
    the next new window will be placed in (Layout.preselect)
    """
    def __init__(self, wm: Layout, output: PyWMOutput, *args: Any, **kwargs: Any):
        PyWMWidget.__init__(self, wm, output, *args, **kwargs)
        self._output = output
        self.set_primitive("rounded_corners_border", [], [
            *get_border_color(conf_color(), ('', '', 0)),
            conf_view_corner_radius() * output.scale,
            conf_width() * output.scale])

    def _box(self) -> Optional[tuple[float, float, float, float]]:
        layout: Layout = self.wm
        if layout.drop_hint is not None:
            ws_handle, i, j, tw, th = layout.drop_hint
        elif layout.preselect is not None:
            (ws_handle, i, j), tw, th = layout.preselect, 1, 1
        else:
            return None
        ws = [w for w in layout.workspaces if w._handle == ws_handle]
        if len(ws) == 0:
            return None
        return layout.tile_box(layout.state, ws[0], i, j, tw, th)

    def process(self) -> PyWMWidgetDownstreamState:
        o = self._output
        box = self._box()
        if box is not None:
            x, y, w, h = box
            if x + w <= o.pos[0] or y + h <= o.pos[1] or o.pos[0] + o.width <= x or o.pos[1] + o.height <= y:
                box = None

        if box is None:
            return PyWMWidgetDownstreamState(0, (o.pos[0], o.pos[1], 0, 0), lock_enabled=False, opacity=0.)
        return PyWMWidgetDownstreamState(10000, box, lock_enabled=False, opacity=1.)
