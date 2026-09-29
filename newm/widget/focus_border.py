from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from ..state import LayoutState
    from ..view import View
    from ..layout import Layout

import logging

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

def _extent() -> float:
    """Distance from the window edge to the edge of the border widget"""
    if conf_style() == 'tron':
        return conf_focus_d() + 4. * conf_tron_glow()
    return conf_focus_d()

class FocusBorder(Animate[PyWMWidgetDownstreamState], PyWMWidget):
    def __init__(self, wm: Layout, output: PyWMOutput, parent: FocusBorders, *args: Any, **kwargs: Any):
        self._output = output
        self._parent = parent
        PyWMWidget.__init__(self, wm, output, *args, **kwargs)
        Animate.__init__(self)

        self._corner_radius = -1.
        self.set_corner_radius(conf_view_corner_radius() + conf_focus_d())

    def set_corner_radius(self, radius: float) -> None:
        if abs(radius - self._corner_radius) < 0.01:
            return
        self._corner_radius = radius
        if conf_style() == 'tron':
            s = self._output.scale
            self.set_primitive("tron_border", [], [
                *parse_color(conf_color()),
                *parse_color(conf_tron_accent()),
                self._corner_radius * s,
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
        return self._process(self.reducer(self._parent.current_box, 1.))

    def _anim_damage(self) -> None:
        self.damage(False)

class FocusBorders(Animatable, DamageTracked):
    def __init__(self, wm: Layout):
        DamageTracked.__init__(self, wm)
        self.wm = wm
        self.borders: list[FocusBorder] = []

        self._skip_next_animate: bool = False

        self.current_view: Optional[View] = None
        self.current_box: tuple[float, float, float, float, float, Optional[tuple[float, float, float, float]]] = -999, 0, 0, 0, 0, None

    def update(self) -> None:
        for b in self.borders:
            b.destroy()
        if conf_enabled():
            self.borders = [self.wm.create_widget(FocusBorder, o, self) for o in self.wm.layout]

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
