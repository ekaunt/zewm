from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from ..state import LayoutState
    from ..view import View
    from ..layout import Layout

import logging
import time

from pywm import PyWMWidget, PyWMWidgetDownstreamState, PyWMOutput, DamageTracked

from ..animate import Animate, Animatable
from ..interpolation import WidgetDownstreamInterpolation
from ..config import configured_value
from ..util import get_border_color, parse_color

logger = logging.getLogger(__name__)

conf_view_corner_radius = configured_value('view.corner_radius', 12)
conf_focus_d = configured_value('focus.distance', 4)
conf_focus_w = configured_value('focus.width', 2)
conf_anim_time = configured_value('focus.anim_time', 0.3)
conf_animate_on_change = configured_value('focus.animate_on_change', False)
conf_enabled = configured_value('focus.enabled', True)
conf_color = configured_value('focus.color', '#19CEEB55')
conf_gradient_primary = configured_value('focus.gradient.primary', '')
conf_gradient_secondary = configured_value('focus.gradient.secondary', '')
conf_gradient_angle = configured_value('focus.gradient.angle', 0)

# 'tron': glowing line with two light streaks racing around it (tron_border shader).
# focus.distance is then the gap from the window edge to the centre of the line.
conf_style = configured_value('focus.style', 'solid')
conf_tron_accent = configured_value('focus.tron.accent_color', '#ff7a18')
conf_tron_glow = configured_value('focus.tron.glow', 6.)
conf_tron_speed = configured_value('focus.tron.speed', 0.2)

# 'callbetter': callbetter.com panel look (tron_cb_border shader): 1px border,
# corner brackets, soft glow, a light traces the border once on focus change.
conf_cb_glow = configured_value('focus.callbetter.glow', 8.)
conf_cb_arm = configured_value('focus.callbetter.bracket', 18.)
conf_cb_gap = configured_value('focus.callbetter.bracket_gap', 3.)
# Two streaks spin slowly round the border: one in focus.color, one in spin_color
conf_cb_spin_color = configured_value('focus.callbetter.spin_color', '#ff7a18')
conf_cb_spin_speed = configured_value('focus.callbetter.spin_speed', 0.0667)  # laps/s
# On a focus change a light cycle rides from the old window to the new one
conf_cb_cycle = configured_value('focus.callbetter.cycle', True)
conf_cb_cycle_color = configured_value('focus.callbetter.cycle_color', '#6ee7b7')
conf_cb_cycle_speed = configured_value('focus.callbetter.cycle_speed', 2400.)  # logical px/s

Box = tuple[float, float, float, float, float, Optional[tuple[float, float, float, float]]]

def _cycle_path(old: Box, new: Box) -> Optional[list[tuple[float, float]]]:
    """
    Right-angle path from the centre of the old box to the border line of the
    new one, in global logical coordinates. The middle leg runs through the gap.
    """
    if old[0] == -999 or new[0] == -999 or old[3] <= 0 or old[4] <= 0 or new[3] <= 0 or new[4] <= 0:
        return None
    d = conf_focus_d()
    ox, oy, ow, oh = old[1] - d, old[2] - d, old[3] + 2*d, old[4] + 2*d
    nx, ny, nw, nh = new[1] - d, new[2] - d, new[3] + 2*d, new[4] + 2*d
    gap_x = max(nx - (ox + ow), ox - (nx + nw))
    gap_y = max(ny - (oy + oh), oy - (ny + nh))
    if gap_x < 0 and gap_y < 0:
        # Overlapping (stacked or tabbed): nowhere to ride
        return None
    sx, sy = ox + ow/2, oy + oh/2
    if gap_x >= gap_y:
        right = nx + nw/2 > sx
        mx = (ox + ow + nx) / 2 if right else (ox + nx + nw) / 2
        ex, ey = (nx if right else nx + nw), ny + nh/2
        return [(sx, sy), (mx, sy), (mx, ey), (ex, ey)]
    down = ny + nh/2 > sy
    my = (oy + oh + ny) / 2 if down else (oy + ny + nh) / 2
    ex, ey = nx + nw/2, (ny if down else ny + nh)
    return [(sx, sy), (sx, my), (ex, my), (ex, ey)]

def _extent() -> float:
    """Distance from the window edge to the edge of the border widget"""
    if conf_style() == 'tron':
        return conf_focus_d() + 4. * conf_tron_glow()
    if conf_style() == 'callbetter':
        return conf_focus_d() + max(4. * conf_cb_glow(), conf_cb_gap() + 3.)
    return conf_focus_d()

class FocusBorder(Animate[PyWMWidgetDownstreamState], PyWMWidget):
    def __init__(self, wm: Layout, output: PyWMOutput, parent: FocusBorders, *args: Any, **kwargs: Any):
        self._output = output
        self._parent = parent
        PyWMWidget.__init__(self, wm, output, *args, **kwargs)
        Animate.__init__(self)

        self._corner_radius = -1.
        self._focus_t = -1.
        # monotonic() when the build-in ends; then _focus_t goes back to -1 so the
        # shader clock wrapping (hourly) cannot replay it
        self._build_end: Optional[float] = None
        self.set_corner_radius(conf_view_corner_radius() + conf_focus_d())

    def trace(self) -> None:
        """Start the light trace of the callbetter style (shader clock: CLOCK_MONOTONIC mod 3600)"""
        if conf_style() != 'callbetter':
            return
        now = time.monotonic()
        self._focus_t = now % 3600.
        self._build_end = now + 2.
        self._corner_radius = -1.
        self.set_corner_radius(self._line_radius)
        self.damage()

    def set_corner_radius(self, radius: float) -> None:
        if abs(radius - self._corner_radius) < 0.01:
            return
        self._corner_radius = radius
        self._line_radius = radius
        if conf_style() == 'callbetter':
            s = self._output.scale
            self.set_primitive("tron_cb_border", [], [
                *parse_color(conf_color()),
                (radius if radius > conf_focus_d() + 0.01 else 0.) * s,
                (_extent() - conf_focus_d()) * s,
                conf_cb_glow() * s,
                self._focus_t,
                conf_cb_arm() * s,
                conf_cb_gap() * s,
                s,
                *parse_color(conf_cb_spin_color())[:3],
                float(conf_cb_spin_speed())])
            return
        if conf_style() == 'tron':
            s = self._output.scale
            self.set_primitive("tron_border", [], [
                *parse_color(conf_color()),
                *parse_color(conf_tron_accent()),
                # Square windows get a square line; rounded ones a concentric one
                (self._corner_radius if self._corner_radius > conf_focus_d() + 0.01 else 0.) * s,
                conf_focus_w() * s,
                (_extent() - conf_focus_d()) * s,
                conf_tron_glow() * s,
                float(conf_tron_speed())])
            return
        self.set_primitive("rounded_corners_border", [], [
            # Color
            *get_border_color(conf_color(), (conf_gradient_primary(), conf_gradient_secondary(), conf_gradient_angle())),
            # Corner radius
            self._corner_radius * self._output.scale,
            # Width
            conf_focus_w() * self._output.scale])

    def reducer(self, box: tuple[float, float, float, float, float, Optional[tuple[float, float, float, float]]], opacity: float) -> PyWMWidgetDownstreamState:
        intersects = True
        if (ws := box[5]) is not None:
            o_box = (self._output.pos[0], self._output.pos[1], self._output.width, self._output.height)
            if o_box[0] + o_box[2] <= ws[0]:
                intersects = False
            elif o_box[1] + o_box[3] <= ws[1]:
                intersects = False
            elif ws[0] + ws[2] <= o_box[0]:
                intersects = False
            elif ws[1] + ws[3] <= o_box[1]:
                intersects = False

        if (box[2] == 0 or box[3] == 0) and getattr(self._parent, 'is_ornament', False):
            # ornament of a view that is still a point (layer_initial): grow from there
            return PyWMWidgetDownstreamState(box[0], (box[1], box[2], 0, 0), lock_enabled=False, opacity=0.)
        if box[2] == 0 or box[3] == 0 or not intersects:
            e = _extent()
            return PyWMWidgetDownstreamState(0, (self._output.pos[0] - e - self._corner_radius,
                                                 self._output.pos[1] - e - self._corner_radius,
                                                 self._output.width + 2*e + 2*self._corner_radius,
                                                 self._output.height + 2*e + 2*self._corner_radius), lock_enabled=False, opacity=opacity)
        else:
            e = _extent()
            return PyWMWidgetDownstreamState(box[0], (box[1] - e, box[2] - e, box[3] + 2*e, box[4] + 2*e), lock_enabled=False, opacity=opacity)

    def animate(self, old_box: tuple[float, float, float, float, float, Optional[tuple[float, float, float, float]]], old_opacity: float, new_box: tuple[float, float, float, float, float, Optional[tuple[float, float, float, float]]], new_opacity: float, dt: float) -> None:
        cur = self.reducer(old_box, old_opacity)
        nxt = self.reducer(new_box, new_opacity)

        self._animate(WidgetDownstreamInterpolation(self.wm, self, cur, nxt), dt)

    def process(self) -> PyWMWidgetDownstreamState:
        if self._build_end is not None:
            if time.monotonic() > self._build_end:
                self._build_end = None
                self._focus_t = -1.
                self._corner_radius = -1.
                self.set_corner_radius(self._line_radius)
            else:
                self.damage()
        return self._process(self.reducer(self._parent.current_box, 1.))

    def _anim_damage(self) -> None:
        self.damage(False)

class LightCycle(PyWMWidget):
    """
    Light cycle riding from the old focused window to the new one
    (tron_cb_cycle shader). Hidden (opacity 0, not drawn) between rides.
    """
    MARGIN = 10.

    def __init__(self, wm: Layout, output: PyWMOutput, *args: Any, **kwargs: Any):
        self._output = output
        PyWMWidget.__init__(self, wm, output, *args, **kwargs)
        self._box: tuple[float, float, float, float] = (0, 0, 1, 1)
        self._end: float = 0.

    def ride(self, path: list[tuple[float, float]], duration: float) -> None:
        x0 = min(x for x, _ in path) - self.MARGIN
        y0 = min(y for _, y in path) - self.MARGIN
        x1 = max(x for x, _ in path) + self.MARGIN
        y1 = max(y for _, y in path) + self.MARGIN
        self._box = (x0, y0, x1 - x0, y1 - y0)
        now = time.monotonic()
        # Travel plus the shader's tail fade
        self._end = now + duration + 0.4
        s = self._output.scale
        self.set_primitive("tron_cb_cycle", [], [
            *[c for x, y in path for c in ((x - x0) * s, (y - y0) * s)],
            *parse_color(conf_cb_cycle_color())[:3],
            now % 3600.,
            duration,
            s])
        self.damage()

    def process(self) -> PyWMWidgetDownstreamState:
        active = time.monotonic() < self._end
        if active:
            # Come back once the ride is over to hide again
            self.damage()
        return PyWMWidgetDownstreamState(900, self._box, lock_enabled=False, opacity=1. if active else 0.)


class ViewOrnament(Animatable, DamageTracked):
    """
    The focus border look (brackets, streaks, build-in) around one view that is
    not focused, e.g. the notification layer surface. Rule: 'ornament': True,
    or {'radius': r} for the corner radius of the line (default: square).
    """
    is_ornament = True

    def __init__(self, wm: Layout, view: View, radius: float=0.):
        DamageTracked.__init__(self, wm)
        self.wm = wm
        self.view = view
        self._radius = radius
        self.borders = [self.wm.create_widget(FocusBorder, o, self) for o in self.wm.layout]
        for b in self.borders:
            b.set_corner_radius(self._radius + conf_focus_d())
            b.trace()

    def _box(self, state: LayoutState) -> Box:
        if self.view.up_state is None:
            return -999, 0, 0, 0, 0, None
        d = self.view.reducer(self.view.up_state, state)
        return d.z_index - 0.01, *d.logical_box, d.workspace

    @property
    def current_box(self) -> Box:
        return self._box(self.wm.state)

    def animate(self, old_state: LayoutState, new_state: LayoutState, dt: float) -> None:
        old, new = self._box(old_state), self._box(new_state)
        for b in self.borders:
            b.animate(old, old_state.background_opacity, new, new_state.background_opacity, dt)

    def flush_animation(self) -> None:
        for b in self.borders:
            b.flush_animation()

    def damage(self, propagate: bool=False) -> None:
        for b in self.borders:
            b.damage()

    def destroy(self) -> None:
        for b in self.borders:
            b.destroy()
        self.borders = []
        self.damage_finish()


class FocusBorders(Animatable, DamageTracked):
    def __init__(self, wm: Layout):
        DamageTracked.__init__(self, wm)
        self.wm = wm
        self.borders: list[FocusBorder] = []
        self.cycles: list[LightCycle] = []

        self._skip_next_animate: bool = False

        self.current_view: Optional[View] = None
        self.current_box: tuple[float, float, float, float, float, Optional[tuple[float, float, float, float]]] = -999, 0, 0, 0, 0, None

    def update(self) -> None:
        for b in self.borders:
            b.destroy()
        for c in self.cycles:
            c.destroy()
        self.borders, self.cycles = [], []
        if conf_enabled():
            self.borders = [self.wm.create_widget(FocusBorder, o, self) for o in self.wm.layout]
            if conf_style() == 'callbetter' and conf_cb_cycle():
                self.cycles = [self.wm.create_widget(LightCycle, o) for o in self.wm.layout]

    def _set_box_and_radius(self, layout_state: Optional[LayoutState]=None) -> None:
        if layout_state is None:
            layout_state = self.wm.state

        if self.current_view is not None and self.current_view.up_state is not None:
            view_down_state = self.current_view.reducer(self.current_view.up_state, layout_state)
            self.current_box = view_down_state.z_index - 0.01, *view_down_state.logical_box, view_down_state.workspace
            if view_down_state.is_fullscreen:
                self.current_box = -999, 0, 0, 0, 0, None
            for b in self.borders:
                b.set_corner_radius(view_down_state.corner_radius + conf_focus_d())
        else:
            self.current_box = -999, 0, 0, 0, 0, None
            for b in self.borders:
                b.set_corner_radius(conf_view_corner_radius() + conf_focus_d())

    def update_focus(self, view: View, present_states: Optional[tuple[Optional[LayoutState], Optional[LayoutState]]]=None) -> None:
        if id(view) == id(self.current_view):
            return

        animate = conf_animate_on_change()
        if present_states is not None:
            self._skip_next_animate = True
            animate = True

        old_box = self.current_box
        self.current_view = view
        self._set_box_and_radius(layout_state=present_states[1] if present_states is not None else None)
        new_box = self.current_box

        path = _cycle_path(old_box, new_box) if self.cycles else None
        if path is not None:
            length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:]))
            duration = min(max(length / max(conf_cb_cycle_speed(), 1.), 0.15), 0.45)
            for c in self.cycles:
                c.ride(path, duration)
        for b in self.borders:
            b.trace()

        # Background parallax follows the focus
        for bg in self.wm.backgrounds:
            bg.damage()

        if animate:
            for b in self.borders:
                b.animate(old_box, 1., new_box, 1., conf_anim_time())
        else:
            self.damage()

    def unfocus(self) -> None:
        self._skip_next_animate = True
        old_box = self.current_box
        self.current_view = None
        self._set_box_and_radius()
        new_box = self.current_box

        for b in self.borders:
            b.animate(old_box, 1., new_box, 1., conf_anim_time())

    def animate(self, old_state: LayoutState, new_state: LayoutState, dt: float) -> None:
        if self._skip_next_animate:
            self._skip_next_animate = False
            return

        if self.current_view is not None and self.current_view.up_state is not None:
            view_old_down_state = self.current_view.reducer(self.current_view.up_state, old_state)
            view_new_down_state = self.current_view.reducer(self.current_view.up_state, new_state)

            old_opacity = old_state.background_opacity
            new_opacity = new_state.background_opacity

            old_box = view_old_down_state.z_index - 0.01, *view_old_down_state.logical_box, view_old_down_state.workspace
            new_box = view_new_down_state.z_index - 0.01, *view_new_down_state.logical_box, view_new_down_state.workspace

            if view_old_down_state.is_fullscreen:
                old_box = -999, 0, 0, 0, 0, None
            if view_new_down_state.is_fullscreen:
                new_box = -999, 0, 0, 0, 0, None

            self.current_box = new_box
            for b in self.borders:
                b.animate(old_box, old_opacity, new_box, new_opacity, dt)

    def flush_animation(self) -> None:
        for b in self.borders:
            b.flush_animation()

    def damage(self, propagate: bool=False) -> None:
        self._set_box_and_radius()

        for b in self.borders:
            b.damage()
