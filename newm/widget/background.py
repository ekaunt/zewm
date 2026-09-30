from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional, cast

import math
import time
import logging

from pywm import PyWMBackgroundWidget, PyWMWidget, PyWMWidgetDownstreamState, PyWMOutput

from ..animate import Animate, Animatable
from ..interpolation import Interpolation
from ..config import configured_value
from ..util import parse_color

if TYPE_CHECKING:
    from ..state import LayoutState
    from ..layout import Layout, Workspace, WorkspaceState

logger = logging.getLogger(__name__)

conf_outputs = configured_value('outputs', cast(list[dict[str, Any]], []))
conf_time_scale = configured_value('background.time_scale', 0.15)
conf_path_default = configured_value('background.path', cast(Optional[str], None))
conf_anim_default = configured_value('background.anim', True)

class BackgroundState:
    def __init__(self, layout_state: LayoutState, ws_state: WorkspaceState, wallpaper_size: tuple[int, int], output_size: tuple[float, float], output_scale: float) -> None:
        x1, y1, x2, y2 = ws_state.get_extent()
        x2 += 1
        y2 += 1

        x1 -= 1
        y1 -= 1
        x2 += 1
        y2 += 1

        vx, vy, vw, vh = ws_state.i, ws_state.j, ws_state.size, ws_state.size

        if vx < x1:
            vw -= (x1 - vx)
            vx = x1
        if vy < y1:
            vy -= (y1 - vy)
            vy = y1
        if vx + vw > x2:
            vw = (x2 - vx)
        if vy + vh > y2:
            vh = (y2 - vy)

        extent = x1, y1, x2 - x1, y2 - y1
        viewpoint = vx, vy, vw, vh
        opacity = layout_state.background_opacity

        vx, vy, vw, vh = viewpoint
        ex, ey, ew, eh = extent

        vx -= ex
        vy -= ey
        # 1. ex, ey == 0, 1

        vx /= ew
        vy /= eh
        vw /= ew
        vh /= eh
        # 2. ew, eh == 1, 1

        vw = min(1, vw)
        vh = min(1, vh)
        vx = max(0, min(1 - vw, vx))
        vy = max(0, min(1 - vh, vy))
        # 3. vx, vy, vw, vh are viewport within [0, 1] x [0, 1]

        width, height = wallpaper_size
        output_width, output_height = output_size
        vx *= width
        vy *= height
        vw *= width
        vh *= height
        # 4. vx, vy, vw, vh are viewport within image resolution

        # if vx < 0 or vx + vw > width or vy < 0 or vy + vh > height:
        #     logger.debug("Background placement issue vx vy vw vh = %f %f %f %f (%f %f)" % (vx, vy, vw, vh, width, height))

        w0 = width / ew
        h0 = height / eh
        w1 = output_width * output_scale
        h1 = output_height * output_scale
        if abs(w0 - width) > 0.1 and abs(h0 - height) > 0.1 and width > w1 and height > h1:
            vwp = width + (w1 - width) / (w0 - width) * (vw - width)
            vhp = height + (h1 - height) / (h0 - height) * (vh - height)
            # 5a. vwp, vhp are target size in same coordiantes as vx, vy, vw, vh

            if abs(vw - vwp) < 0.1 or abs(vh - vhp) < 0.1:
                vxp = vx
                vyp = vy
            else:
                vxp = (width - vwp) / (width - vw) * vx
                vyp = (height - vhp) / (height - vh) * vy
            # 5b. vxp, vyp are corresponding coordinates

        else:
            vxp, vyp, vwp, vhp = vx, vy, vw, vh

        # if vxp < 0 or vxp + vwp > width or vyp < 0 or vyp + vhp > height:
        #     logger.debug("Background placement issue vxp vyp vwp vhp = %f %f %f %f (%f %f)" % (vxp, vyp, vwp, vhp, width, height))

        x, y, w, h = vxp, vyp, vwp, vhp
        if w/h < output_width/output_height:
            new_h = output_height * w/output_width
            y -= (new_h - h)/2.
            h = new_h
        else:
            new_w = output_width * h/output_height
            x -= (new_w - w)/2.
            w = new_w
        # 6. x, y, w, h are possibly shrinked to account for aspect ratio

        # Safety net - should not be necessary
        scale_fac = 1.
        if w > width:
            scale_fac = width / w
        if h > height:
            scale_fac = min(scale_fac, height / h)
        w, h = scale_fac*w, scale_fac*h


        if x < 0:
            x = 0
        if y < 0:
            y = 0
        if x + w > width:
            x = width - w
        if y + h > height:
            y = height - h

        # if x < 0 or x + w > width or y < 0 or y + h > height:
        #     logger.debug("Background placement issue x y w h = %f %f %f %f (%f %f)" % (x, y, w, h, width, height))

        # if w < w1 or h < h1:
        #     logger.debug("Background scaling issue: %dx%d on %dx%d wallpaper" % (w, h, width, height))

        fx, fy = -x * output_width / w, -y * output_height / h
        fw, fh = width * output_width / w, height * output_height / h
        # 7. fx, fy, fw, fh are transformed to output coordinates

        # if height > 0 and fh > 0 and abs(fw / fh - width / height) > 0.01:
        #     logger.debug("Background aspect ratio issue: %dx%d on %dx%d wallpaper" % (fw, fh, width, height))

        self.box = (fx, fy, float(math.ceil(fw)), float(math.ceil(fh)))
        self.opacity = opacity

    def set_max(self, wallpaper_size: tuple[int, int], output_size: tuple[float, float]) -> None:
        self.opacity = 1.
        x, y, w, h = 0., 0., float(output_size[0]), float(output_size[1])
        if w/h > wallpaper_size[0]/wallpaper_size[1]:
            new_h = wallpaper_size[1] * w/wallpaper_size[0]
            y -= (new_h - h)/2.
            h = new_h
        else:
            new_w = wallpaper_size[0] * h/wallpaper_size[1]
            x -= (new_w - w)/2.
            w = new_w
        self.box = (x, y, math.ceil(w), math.ceil(h))

    def delta(self, other: BackgroundState) -> float:
        return abs(self.box[0] - other.box[0]) + \
            abs(self.box[1] - other.box[1]) + \
            abs(self.box[2] - other.box[2]) + \
            abs(self.box[3] - other.box[3]) + \
            1000 * abs(self.opacity - other.opacity)

    def approach(self, other: BackgroundState, time_scale: float, dt: float) -> None:
        db = other.box[0] - self.box[0], other.box[1] - self.box[1], other.box[2] - self.box[2], other.box[3] - self.box[3]
        do = other.opacity - self.opacity
        factor = dt / time_scale

        factor = min(1, factor)
        self.opacity += do*factor
        self.box = self.box[0] + db[0] * factor, self.box[1] + db[1] * factor, self.box[2] + db[2] * factor, self.box[3] + db[3] * factor

    def __str__(self) -> str:
        return "<BackgroundState box=%s opacity=%f>" % (str(self.box), self.opacity)


class Background(PyWMBackgroundWidget, Animatable):
    def __init__(self, wm: Layout, output: PyWMOutput, workspace: Workspace, *args: Any, **kwargs: Any):

        self._output: PyWMOutput = output
        self._workspace: Workspace = workspace

        self._prevent_anim = not conf_anim_default()
        if self._workspace.prevent_anim:
            self._prevent_anim = True

        path = None
        for o in conf_outputs():
            if o['name'] == output.name:
                if 'background' in o:
                    if 'path' in o['background']:
                        path = o['background']['path']
                    if 'anim' in o['background'] and not o['background']['anim']:
                        self._prevent_anim = True

        if path is None:
            path = conf_path_default()

        PyWMBackgroundWidget.__init__(self, wm, output, path, *args, **kwargs)

        self._current_state = BackgroundState(self.wm.state, self.wm.state.get_workspace_state(self._workspace), (self.width, self.height), (self._output.width, self._output.height), self._output.scale)
        self._target_state = BackgroundState(self.wm.state, self.wm.state.get_workspace_state(self._workspace), (self.width, self.height), (self._output.width, self._output.height), self._output.scale)
        self._last_frame: float = 0.
        self._anim_caught: Optional[float] = None

        if self._prevent_anim:
            self._current_state.set_max((self.width, self.height), (self._output.width, self._output.height))


    def animate(self, old_state: LayoutState, new_state: LayoutState, dt: float) -> None:
        if self._prevent_anim:
            return

        self._anim_caught = -dt
        self._target_state = BackgroundState(new_state, new_state.get_workspace_state(self._workspace), (self.width, self.height), (self._output.width, self._output.height), self._output.scale)

        self.damage()

    def flush_animation(self) -> None:
        self._anim_caught = None

    def process(self) -> PyWMWidgetDownstreamState:
        if not self._prevent_anim:
            # State handling
            t = time.time()

            if self._anim_caught is None:
                target_state = BackgroundState(self.wm.state, self.wm.state.get_workspace_state(self._workspace), (self.width, self.height), (self._output.width, self._output.height), self._output.scale)
                if target_state.delta(self._target_state) > 1:
                    self._target_state = target_state
            else:
                if self._anim_caught < 0:
                    self._anim_caught = t - 1./120. - self._anim_caught
                    self._last_frame = t - 1./120.


            if self._current_state.delta(self._target_state) > 1:
                self._current_state.approach(self._target_state, conf_time_scale(), t - self._last_frame)
                self.damage()
            elif self._current_state != self._target_state:
                self._current_state = self._target_state
                self.damage()

            self._last_frame = t

        result = PyWMWidgetDownstreamState()
        result.z_index = -10000
        result.opacity = self._current_state.opacity
        result.box = (self._output.pos[0] + self._current_state.box[0], self._output.pos[1] + self._current_state.box[1], self._current_state.box[2], self._current_state.box[3])
        return result



conf_tron_grid_color = configured_value('background.tron.grid_color', '#18cae6')
conf_tron_accent_color = configured_value('background.tron.accent_color', '#ff7a18')
conf_tron_speed = configured_value('background.tron.speed', 0.6)
# Seconds the parallax layers take to catch up after a move (glide)
conf_tron_glide = configured_value('background.tron.glide', 0.)

TronGridState = tuple[float, float, float, float, float]

class _TronGridInterpolation(Interpolation[TronGridState]):
    """Linear in screen space, like the views, so the grid stays on the tiles"""
    def __init__(self, s0: TronGridState, s1: TronGridState) -> None:
        self.s0, self.s1 = s0, s1

    def get(self, at: float) -> TronGridState:
        at = min(1., max(0., at))
        a, b = self.s0, self.s1
        return (a[0] + (b[0] - a[0]) * at, a[1] + (b[1] - a[1]) * at, a[2] + (b[2] - a[2]) * at,
                a[3] + (b[3] - a[3]) * at, a[4] + (b[4] - a[4]) * at)

class TronBackground(Animate[TronGridState], PyWMWidget, Animatable):
    """
    Animated 2D grid rendered by the tron_grid primitive shader instead of a
    wallpaper image. Its front layer is the tile grid of the workspace.
    """
    def __init__(self, wm: Layout, output: PyWMOutput, workspace: Workspace, *args: Any, **kwargs: Any):
        PyWMWidget.__init__(self, wm, output, *args, **kwargs)
        Animate.__init__(self)
        self._output: PyWMOutput = output
        self._workspace: Workspace = workspace
        self._anchor: tuple[float, float] = (0., 0.)
        self._last_params: Optional[list[float]] = None
        # Smoothed camera (centre x, centre y, tiles across) and its velocity
        self._cam: Optional[tuple[float, float, float]] = None
        self._vel: tuple[float, float] = (0., 0.)
        self._cam_t: float = 0.

    def _grid(self, state: LayoutState) -> TronGridState:
        """(tile w, tile h, x of tile 0, y of tile 0, opacity) in output coordinates"""
        ws = self._workspace
        ws_state = state.get_workspace_state(ws)
        h_eff = ws.height - ws_state.top_excluded - ws_state.bottom_excluded
        tw = ws.width / ws_state.size
        th = h_eff / ws_state.size
        ox = ws.pos_x - self._output.pos[0] - ws_state.i * tw
        oy = ws.pos_y - self._output.pos[1] + ws_state.top_excluded - ws_state.j * th
        return tw, th, ox, oy, state.background_opacity

    def animate(self, old_state: LayoutState, new_state: LayoutState, dt: float) -> None:
        self._animate(_TronGridInterpolation(self._grid(old_state), self._grid(new_state)), dt)

    def _anim_damage(self) -> None:
        self.damage()

    def process(self) -> PyWMWidgetDownstreamState:
        tw, th, ox, oy, opacity = self._process(self._grid(self.wm.state))

        # Light cycles start near the view; move their home only when it drifts away
        cx = (0.5 * self._output.width - ox) / tw
        cy = (0.5 * self._output.height - oy) / th
        if abs(cx - self._anchor[0]) > 2 or abs(cy - self._anchor[1]) > 2:
            self._anchor = (float(round(cx)), float(round(cy)))

        # Parallax camera eases toward the real one: the layers keep sliding after a move
        target = (cx, cy, self._output.width / tw)
        t = time.time()
        if self._cam is None or conf_tron_glide() <= 0:
            # No glide: layers move exactly with the windows, just at their parallax rate
            self._cam = target
            self._vel = (0., 0.)
        else:
            dt = min(max(t - self._cam_t, 0.), 0.1)
            k = 1. - math.exp(-dt / max(conf_tron_glide(), 1e-3))
            cam = tuple(c + (g - c) * k for c, g in zip(self._cam, target))
            if dt > 0:
                self._vel = ((cam[0] - self._cam[0]) / dt, (cam[1] - self._cam[1]) / dt)
            self._cam = cast(tuple[float, float, float], cam)
            if max(abs(g - c) for c, g in zip(self._cam, target)) > 1e-3:
                self.damage()
            else:
                self._cam = target
                self._vel = (0., 0.)
        self._cam_t = t

        s = self._output.scale
        params = [tw * s, th * s, ox * s, oy * s,
                  *parse_color(conf_tron_grid_color())[:3],
                  *parse_color(conf_tron_accent_color())[:3],
                  *self._anchor,
                  float(conf_tron_speed()),
                  *self._cam, *self._vel]
        if params != self._last_params:
            self._last_params = params
            self.set_primitive("tron_grid", [], params)

        result = PyWMWidgetDownstreamState()
        result.z_index = -10000
        result.opacity = opacity
        result.box = (self._output.pos[0], self._output.pos[1], self._output.width, self._output.height)
        return result
