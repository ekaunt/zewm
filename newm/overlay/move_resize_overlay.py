from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from threading import Thread
import time
import logging

from pywm import PYWM_PRESSED, PyWMModifiers

from .overlay import Overlay
from ..grid import Grid
from ..hysteresis import Hysteresis
from ..config import configured_value
from ..gestures import GestureListener, LowpassGesture, Gesture


if TYPE_CHECKING:
    from ..layout import Layout, Workspace
    from ..view import View
    from ..state import LayoutState

logger = logging.getLogger(__name__)

conf_move_grid_ovr = configured_value("move.grid_ovr", 0.2)
conf_move_grid_m = configured_value("move.grid_m", 3)
conf_resize_grid_ovr = configured_value("resize.grid_ovr", 0.1)
conf_resize_grid_m = configured_value("resize.grid_m", 3)
conf_hyst = configured_value("resize.hyst", 0.2)
conf_gesture_factor = configured_value("move_resize.gesture_factor", 2)
conf_anim_t = configured_value("anim_time", .3)

conf_lp_freq = configured_value('gestures.lp_freq', 60.)
conf_lp_inertia = configured_value('gestures.lp_inertia', .8)

conf_gesture_binding_move_resize = configured_value("gesture_bindings.move_resize", ("L", "move-1", "swipe-2"))

# Mod+drag moves the window 1:1 with the pointer; dropping on a window's edge shoves it toward that edge, on its center tabs
conf_follow_cursor = configured_value("move_resize.follow_cursor", False)
# fraction of a window's width/height counted as its edge when dropping onto it
conf_shove_edge = configured_value("move_resize.shove_edge", 0.25)
conf_c_scale = configured_value('gestures.c.scale_px', 800.)

class _Overlay:
    def reset_gesture(self) -> None:
        pass

    def on_gesture(self, values: dict[str, float]) -> None:
        pass

    def close(self) -> tuple[Workspace, float, float, float, float, float, float, float, float, float]:
        pass


class MoveOverlay(_Overlay):
    def __init__(self, layout: Layout, view: View) -> None:
        self.layout = layout
        self.workspace = layout.workspaces[0]
        self.ws_state = self.layout.state.get_workspace_state(self.workspace)

        self.view = view
        self.i = 0.
        self.j = 0.
        self.w = 1.
        self.h = 1.

        # In case of switched workspace
        self.di = 0.
        self.dj = 0.

        try:
            view_state, self.ws_state, ws_handle = self.layout.state.find_view(self.view)
            self.workspace = [w for w in self.layout.workspaces if w._handle == ws_handle][0]
            self.i = view_state.i
            self.j = view_state.j
            self.w = view_state.w
            self.h = view_state.h

            self.layout.update(
                self.layout.state.setting_workspace_state(
                    self.workspace, self.ws_state.replacing_view_state(
                        self.view,
                        move_origin=(self.i, self.j, self.workspace)
                    )))
        except Exception:
            logger.warn("Unexpected: Could not access view %s state", self.view)

        self.i_grid = Grid("i", round(self.i - 3), round(self.i + 3), self.i, conf_move_grid_ovr(), conf_move_grid_m())
        self.j_grid = Grid("j", round(self.j - 3), round(self.j + 3), self.j, conf_move_grid_ovr(), conf_move_grid_m())

        self.last_dx = 0.
        self.last_dy = 0.

        self._closed = False

    def reset_gesture(self) -> None:
        self.last_dx = 0
        self.last_dy = 0

    def on_gesture(self, values: dict[str, float]) -> None:
        if self._closed:
            return

        factor = conf_gesture_factor() * self.ws_state.size

        self.i += factor*(values['delta_x'] - self.last_dx)
        self.j += factor*(values['delta_y'] - self.last_dy)

        i0 = self.i_grid.at(self.i)
        j0 = self.j_grid.at(self.j)

        self.last_dx = values['delta_x']
        self.last_dy = values['delta_y']

        i0 += self.di
        j0 += self.dj

        workspace, i, j, self.w, self.h = self.view.transform_to_closest_ws(self.workspace, i0, j0, self.w, self.h)

        if workspace != self.workspace:
            logger.debug("Move - switching workspace %d (%f %f)-> %d (%f %f)" % (self.workspace._handle, i0, j0, workspace._handle, i, j))
            self.di += (i - i0)
            self.dj += (j - j0)

            self.layout.state.move_view_state(self.view, self.workspace, workspace)
            self.workspace = workspace

        self.layout.state.update_view_state(
            self.view, i=i, j=j, w=self.w, h=self.h)
        self.layout.damage()

    def close(self) -> tuple[Workspace, float, float, float, float, float, float, float, float, float]:
        self._closed = True

        try:
            state, self.ws_state, ws_handle = self.layout.state.find_view(self.view)
            self.workspace = [w for w in self.layout.workspaces if w._handle == ws_handle][0]

            fi: float = 0.
            fj: float = 0.
            fi, ti = self.i_grid.final()
            fj, tj = self.j_grid.final()

            fi += self.di
            fj += self.dj

            workspace, fi, fj, _, __ = self.view.transform_to_closest_ws(self.workspace, fi, fj, self.w, self.h)

            fi = round(fi)
            fj = round(fj)

            self.w = max(1, round(self.w)) 
            self.h = max(1, round(self.h)) 

            if workspace != self.workspace:
                logger.debug("Move - switching workspace %d -> %d" % (self.workspace._handle, workspace._handle))
                self.layout.state.move_view_state(self.view, self.workspace, workspace)
                self.workspace = workspace

            logger.debug("Move - Grid finals: %f %f (%f %f)", fi, fj, ti, tj)

            return self.workspace, state.i, state.j, state.w, state.h, fi, fj, round(self.w), round(self.h), max(ti, tj)
        except Exception:
            logger.warn("Unexpected: Could not access view %s state... returning default placement", self.view)
            return self.workspace, self.i, self.j, 1, 1, round(self.i), round(self.j), 1, 1, 1


class ResizeOverlay(_Overlay):
    def __init__(self, layout: Layout, view: View):
        self.layout = layout
        self.workspace = layout.workspaces[0]
        self.ws_state = self.layout.state.get_workspace_state(self.workspace)

        self.view = view
        self.i = 0.
        self.j = 0.
        self.w = 1.
        self.h = 1.

        self.hyst_w = lambda v: v
        self.hyst_h = lambda v: v

        try:
            view_state, self.ws_state, ws_handle = self.layout.state.find_view(self.view)
            self.workspace = [w for w in self.layout.workspaces if w._handle == ws_handle][0]
            self.i = view_state.i
            self.j = view_state.j
            self.w = view_state.w
            self.h = view_state.h

            self.hyst_w = Hysteresis(conf_hyst(), self.w)
            self.hyst_h = Hysteresis(conf_hyst(), self.h)

            self.layout.update(
                self.layout.state.setting_workspace_state(
                    self.workspace, self.ws_state.replacing_view_state(
                        self.view,
                        move_origin=(self.i, self.j, self.workspace),
                        scale_origin=(self.w, self.h)
                    )))

        except Exception:
            logger.warn("Unexpected: Could not access view %s state", self.view)


        self.i_grid = Grid("i", round(self.i - 3), round(self.i + 3), self.i, conf_move_grid_ovr(), conf_move_grid_m())
        self.j_grid = Grid("j", round(self.j - 3), round(self.j + 3), self.j, conf_move_grid_ovr(), conf_move_grid_m())
        self.w_grid = Grid("w", 1, round(self.w + 3), self.w, conf_resize_grid_ovr(), conf_resize_grid_m())
        self.h_grid = Grid("h", 1, round(self.h + 3), self.h, conf_resize_grid_ovr(), conf_resize_grid_m())

        self._closed = False

    def on_gesture(self, values: dict[str, float]) -> None:
        if self._closed:
            return

        factor = conf_gesture_factor() * self.ws_state.size
        dw = factor*values['delta_x']
        dh = factor*values['delta_y']

        i, j, w, h = self.i, self.j, self.w, self.h

        if self.w + dw < 1:
            d = 1 - (self.w + dw)
            i = self.i - d
            w = 1 + d
        else:
            i = self.i
            w = self.w + dw

        if self.h + dh < 1:
            d = 1 - (self.h + dh)
            j = self.j - d
            h = 1 + d
        else:
            j = self.j
            h = self.h + dh

        w_ = self.w_grid.at(w)
        h_ = self.h_grid.at(h)
        self.layout.state.update_view_state(
            self.view, i=self.i_grid.at(i), j=self.j_grid.at(j),
            w=w_, h=h_,
            scale_origin=(self.hyst_w(w_),self.hyst_h(h_))
        )

        self.layout.damage()


    def close(self) -> tuple[Workspace, float, float, float, float, float, float, float, float, float]:
        self._closed = True

        try:
            state = self.layout.state.get_view_state(self.view)
            fi, ti = self.i_grid.final()
            fj, tj = self.j_grid.final()
            fw, tw = self.w_grid.final()
            fh, th = self.h_grid.final()

            logger.debug("Resize - Grid finals: %f %f %f %f (%f %f %f %f)", fi, fj, fw, fh, ti, tj, tw, th)

            return self.workspace, state.i, state.j, state.w, state.h, fi, fj, fw, fh, max(ti, tj, tw, th)
        except Exception:
            logger.warn("Unexpected: Could not access view %s state... returning default placement", self.view)
            return self.workspace, self.i, self.j, self.w, self.h, self.i, self.j, self.w, self.h, 1



def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


class CursorMoveOverlay(_Overlay):
    """
    Move a tiled view so it stays under the pointer. On drop:
    - empty space: snap to the nearest tile
    - center of another window: tab onto it (take its box -> stacked)
    - edge of another window: take its place and shove it (and whatever it bumps into)
      out toward the hovered side
    """
    def __init__(self, layout: Layout, view: View) -> None:
        self.layout = layout
        self.view = view
        self.workspace = layout.workspaces[0]
        self.i, self.j, self.w, self.h = 0., 0., 1., 1.

        try:
            view_state, ws_state, ws_handle = self.layout.state.find_view(self.view)
            self.workspace = [w for w in self.layout.workspaces if w._handle == ws_handle][0]
            self.i, self.j, self.w, self.h = view_state.i, view_state.j, view_state.w, view_state.h
            self.layout.update(
                self.layout.state.setting_workspace_state(
                    self.workspace, ws_state.replacing_view_state(
                        self.view,
                        move_origin=(self.i, self.j, self.workspace)
                    )))
        except Exception:
            logger.warn("Unexpected: Could not access view %s state", self.view)

        self.cursor0 = self.layout.cursor_pos
        ci, cj = self._to_tile(*self.cursor0)
        self.grab = ci - self.i, cj - self.j

        self.base = (0., 0.)
        self.last = (0., 0.)
        self.cursor = self.cursor0

        # final i, j, w, h and {view handle: (i, j)} of shoved views
        self.drop: tuple[float, float, float, float] = (round(self.i), round(self.j), round(self.w), round(self.h))
        self.shoves: dict[int, tuple[int, int]] = {}

        # other tiled views as they were before the drag; hover tests and shoves are computed
        # against these so the live preview doesn't feed back into itself
        ws_state = self.layout.state.get_workspace_state(self.workspace)
        self.orig: dict[int, tuple[float, float, float, float]] = {
            h: (s.i, s.j, s.w, s.h) for h, s in ws_state._view_states.items()
            if s.is_tiled and s.swallowed is None and h != self.view._handle}
        self._last_tick = time.time()

    def _to_tile(self, x: float, y: float) -> tuple[float, float]:
        ws = self.workspace
        ws_state = self.layout.state.get_workspace_state(ws)
        h = ws.height - ws_state.top_excluded - ws_state.bottom_excluded
        return (ws_state.i + (x - ws.pos_x) * ws_state.size / ws.width,
                ws_state.j + (y - ws.pos_y - ws_state.top_excluded) * ws_state.size / h)

    def reset_gesture(self) -> None:
        # a new gesture segment (the pointer provider ends one after a short pause) continues from here
        self.base = self.base[0] + self.last[0], self.base[1] + self.last[1]
        self.last = (0., 0.)

    def on_gesture(self, values: dict[str, float]) -> None:
        self.last = values['delta_x'] * conf_c_scale(), values['delta_y'] * conf_c_scale()

        ws = self.workspace
        x = min(max(self.cursor0[0] + self.base[0] + self.last[0], ws.pos_x), ws.pos_x + ws.width - 1)
        y = min(max(self.cursor0[1] + self.base[1] + self.last[1], ws.pos_y), ws.pos_y + ws.height - 1)
        self.cursor = (x, y)

        ci, cj = self._to_tile(x, y)
        self.i, self.j = ci - self.grab[0], cj - self.grab[1]
        self.layout.state.update_view_state(self.view, i=self.i, j=self.j)

        self._compute_drop(ci, cj)
        self.layout.drop_hint = (ws._handle, *self.drop)
        self.layout.update_cursor(True, (int(x), int(y)))
        self.layout.damage()

    def _compute_drop(self, ci: float, cj: float) -> None:
        aw, ah = max(1, round(self.w)), max(1, round(self.h))

        hovered = None
        for oi, oj, ow, oh in self.orig.values():
            if oi <= ci < oi + ow and oj <= cj < oj + oh:
                hovered = (oi, oj, ow, oh)
                break

        self.shoves = {}
        if hovered is None:
            self.drop = (round(self.i), round(self.j), aw, ah)
            return

        oi, oj, ow, oh = hovered
        bi, bj, bw, bh = round(oi), round(oj), max(1, round(ow)), max(1, round(oh))
        fx, fy = (ci - oi) / ow, (cj - oj) / oh
        sides = {'left': fx, 'right': 1 - fx, 'top': fy, 'bottom': 1 - fy}
        side = min(sides, key=lambda k: sides[k])

        if sides[side] >= conf_shove_edge():
            self.drop = (bi, bj, bw, bh)
            return

        target, d = {
            'left': ((bi, bj, aw, ah), (-aw, 0)),
            'right': ((bi + bw - aw, bj, aw, ah), (aw, 0)),
            'top': ((bi, bj, aw, ah), (0, -ah)),
            'bottom': ((bi, bj + bh - ah, aw, ah), (0, ah)),
        }[side]
        self.drop = target

        boxes = {h: (round(b[0]), round(b[1]), max(1, round(b[2])), max(1, round(b[3]))) for h, b in self.orig.items()}
        frontier = [target]
        while frontier:
            nxt = []
            for f in frontier:
                for h, b in boxes.items():
                    if h not in self.shoves and _overlaps(f, b):
                        nb = (b[0] + d[0], b[1] + d[1], b[2], b[3])
                        self.shoves[h] = (nb[0], nb[1])
                        nxt.append(nb)
            frontier = nxt

    def _targets(self) -> dict[int, tuple[float, float]]:
        return {h: self.shoves.get(h, (b[0], b[1])) for h, b in self.orig.items()}  # type: ignore

    def tick(self) -> None:
        """
        Live preview: ease the other views toward where the current drop would put them
        """
        t = time.time()
        k = min(1., (t - self._last_tick) / max(0.01, conf_anim_t()) * 3.)
        self._last_tick = t

        moved = False
        for h, (ti, tj) in self._targets().items():
            v = self.layout._views.get(h)
            if v is None:
                continue
            try:
                s = self.layout.state.get_view_state(v)
            except Exception:
                continue
            if abs(s.i - ti) < 0.005 and abs(s.j - tj) < 0.005:
                if (s.i, s.j) != (ti, tj):
                    self.layout.state.update_view_state(v, i=ti, j=tj)
                    moved = True
                continue
            self.layout.state.update_view_state(v, i=s.i + (ti - s.i) * k, j=s.j + (tj - s.j) * k)
            moved = True
        if moved:
            self.layout.damage()

    def close(self) -> tuple[Workspace, float, float, float, float, float, float, float, float, float]:
        self.layout.drop_hint = None
        self.layout.damage()
        # every other view gets an explicit final position (shoved or restored) for the exit animation
        self.shoves = self._targets()  # type: ignore
        fi, fj, fw, fh = self.drop
        return self.workspace, self.i, self.j, self.w, self.h, fi, fj, fw, fh, conf_anim_t()


class MoveResizeOverlay(Overlay, Thread):
    def __init__(self, layout: Layout, view: View):
        Overlay.__init__(self, layout)
        Thread.__init__(self)

        self.layout.update_cursor(False)

        self.view = view
        self.workspace = layout.workspaces[0]
        self.ws_state = self.layout.state.get_workspace_state(self.workspace)

        try:
            view_state, self.ws_state, ws_handle = self.layout.state.find_view(self.view)
            self.workspace = [w for w in self.layout.workspaces if w._handle == ws_handle][0]
        except:
            logger.warn("Unexpected: Could not access view %s state", self.view)

        self.overlay: Optional[_Overlay] = None

        """
        If move has been finished and we are animating towards final position
            (view initial i, view initial j, view final i, view final j, initial time, finished time)
        """
        self._target_view_pos: Optional[tuple[float, float, float, float, float, float]] = None

        """
        If resize has been finished and we are animating towards final size
            (view initial w, view initial h, view final w, view final h, initial time, finished time)
        """
        self._target_view_size: Optional[tuple[float, float, float, float, float, float]] = None

        """
        If we are adjusting viewpoint (after gesture finished or during)
            (layout initial i, layout initial j, layout final i, layout final j, initial time, finished time)
        """
        self._target_layout_pos: Optional[tuple[float, float, float, float, float, float]] = None
        
        # views pushed aside by a CursorMoveOverlay drop, applied on exit
        self._shoves: dict[int, tuple[int, int]] = {}
        self._cursor_final: Optional[tuple[float, float]] = None

        self._running = True
        self._wants_close = False

    def post_init(self) -> None:
        logger.debug("MoveResizeOverlay: Starting thread...")
        self.start()

    def run(self) -> None:
        while self._running:
            t = time.time()

            in_prog = False
            ovr = self.overlay
            if isinstance(ovr, CursorMoveOverlay):
                ovr.tick()

            if self._target_view_pos is not None:
                in_prog = True
                ii, ij, fi, fj, it, ft = self._target_view_pos
                if t > ft:
                    self.layout.state.update_view_state(self.view, i=fi, j=fj)
                    self._target_view_pos = None
                else:
                    perc = (t-it)/(ft-it)
                    self.layout.state.update_view_state(self.view, i=ii + perc*(fi-ii), j=ij + perc*(fj-ij))
                self.layout.damage()


            if self._target_view_size is not None:
                in_prog = True
                iw, ih, fw, fh, it, ft = self._target_view_size
                if t > ft:
                    self.layout.state.update_view_state(self.view, w=fw, h=fh, scale_origin=None)
                    self._target_view_size = None
                else:
                    perc = (t-it)/(ft-it)
                    self.layout.state.update_view_state(self.view, w=iw + perc*(fw-iw), h=ih + perc*(fh-ih))
                self.layout.damage()

            if self._target_layout_pos is not None:
                in_prog = True
                ii, ij, fi, fj, it, ft = self._target_layout_pos
                if t > ft:
                    self.ws_state.i = fi
                    self.ws_state.j = fj
                    self._target_layout_pos = None
                else:
                    perc = (t-it)/(ft-it)
                    self.ws_state.i=ii + perc*(fi-ii)
                    self.ws_state.j=ij + perc*(fj-ij)
                self.layout.damage()

            elif self.overlay is not None:
                try:
                    view_state = self.layout.state.get_view_state(self.view)
                    i, j, w, h = view_state.i, view_state.j, view_state.w, view_state.h
                    i, j, w, h = round(i), round(j), round(w), round(h)

                    fi, fj = self.ws_state.i, self.ws_state.j

                    if i + w > fi + self.ws_state.size:
                        fi = i + w - self.ws_state.size

                    if j + h > fj + self.ws_state.size:
                        fj = j + h - self.ws_state.size

                    if i < fi:
                        fi = i

                    if j < fj:
                        fj = j

                    if fi != self.ws_state.i or fj != self.ws_state.j:
                        logger.debug("MoveResizeOverlay: Adjusting viewpoint (%f %f) -> (%f %f)",
                                     self.ws_state.i, self.ws_state.j, fi, fj)
                        self._target_layout_pos = (self.ws_state.i, self.ws_state.j, fi, fj, t, t + conf_anim_t())

                except Exception:
                    logger.warn("Unexpected: Could not access view %s state", self.view)

            if not in_prog and self._wants_close:
                self._running = False

            time.sleep(1. / 120.)

        logger.debug("MoveResizeOverlay: Thread finished")
        self.layout.exit_overlay()

    def on_gesture(self, gesture: Gesture) -> bool:
        if not self._running or self._wants_close:
            logger.debug("MoveResizeOverlay: Rejecting gesture")
            return False

        if gesture.kind == conf_gesture_binding_move_resize()[2]:
            logger.debug("MoveResizeOverlay: New TwoFingerSwipePinch")
            if isinstance(self.overlay, CursorMoveOverlay):
                self._close_inner()
            self._target_view_pos = None
            self._target_view_size = None

            self.overlay = ResizeOverlay(self.layout, self.view)
            LowpassGesture(gesture, conf_lp_inertia(), conf_lp_freq()).listener(GestureListener(
                self.overlay.on_gesture,
                self.finish
            ))
            return True

        if gesture.kind == conf_gesture_binding_move_resize()[1] and conf_follow_cursor():
            if isinstance(self.overlay, CursorMoveOverlay):
                self.overlay.reset_gesture()
            else:
                self._target_view_pos = None
                self.overlay = CursorMoveOverlay(self.layout, self.view)
            ovr = self.overlay
            def segment_finished() -> None:
                # pointer pauses end the gesture; only drop once the modifier is released
                if self.overlay is ovr and not self.layout.modifiers.has(conf_gesture_binding_move_resize()[0]):
                    self.finish()
            gesture.listener(GestureListener(ovr.on_gesture, segment_finished))
            return True

        if gesture.kind == conf_gesture_binding_move_resize()[1]:
            logger.debug("MoveResizeOverlay: New SingleFingerMove")
            self._target_view_pos = None

            self.overlay = MoveOverlay(self.layout, self.view)
            LowpassGesture(gesture, conf_lp_inertia(), conf_lp_freq()).listener(GestureListener(
                self.overlay.on_gesture,
                self.finish
            ))
            return True

        return False


    def _close_inner(self) -> None:
        if self.overlay is not None:
            ovr = self.overlay
            ws, ii, ij, iw, ih, fi, fj, fw, fh, t = ovr.close()
            self.overlay = None
            if isinstance(ovr, CursorMoveOverlay):
                self._shoves = ovr.shoves
                self._cursor_final = ovr.cursor

            self.workspace = ws
            if ii != fi or ij != fj:
                self._target_view_pos = (ii, ij, fi, fj, time.time(), time.time() + t)
            if iw != fw or ih != fh:
                self._target_view_size = (iw, ih, fw, fh, time.time(), time.time() + t)

    def finish(self) -> None:
        logger.debug("MoveResizeOverlay: Finishing gesture")
        self._close_inner()

        if not self.layout.modifiers.has(conf_gesture_binding_move_resize()[0]):
            logger.debug("MoveResizeOverlay: Requesting close after gesture finish")
            self.close()

    def on_motion(self, time_msec: int, delta_x: float, delta_y: float) -> bool:
        return False

    def on_axis(self, time_msec: int, source: int, orientation: int, delta: float, delta_discrete: int) -> bool:
        return False

    def on_modifiers(self, modifiers: PyWMModifiers, last_modifiers: PyWMModifiers) -> bool:
        if last_modifiers.pressed(modifiers).has(conf_gesture_binding_move_resize()[0]):
            if self.overlay is None:
                logger.debug("MoveResizeOverlay: Requesting close after Mod release")
                self.close()
            elif isinstance(self.overlay, CursorMoveOverlay):
                logger.debug("MoveResizeOverlay: Dropping after Mod release")
                self.close()
            return True
        return False

    def close(self) -> None:
        if isinstance(self.overlay, CursorMoveOverlay):
            self._close_inner()
        elif self.overlay is not None:
            self.overlay.close()
        self._wants_close = True

    def pre_destroy(self) -> None:
        self._running = False

    def _exit_transition(self) -> tuple[Optional[LayoutState], float]:
        if self._cursor_final is not None:
            self.layout.update_cursor(True, (int(self._cursor_final[0]), int(self._cursor_final[1])))
        else:
            self.layout.update_cursor(True)
        try:
            # Clean up any possible mishaps - should not be necessary
            view_state = self.layout.state.get_view_state(self.view)
            i = round(view_state.i)
            j = round(view_state.j)
            w = round(view_state.w)
            h = round(view_state.h)

            logger.debug("MoveResizeOverlay: Exiting with animation %d, %d, %d, %d -> %d, %d, %d, %d",
                          view_state.i, view_state.j, view_state.w, view_state.h, i, j, w, h)

            state = self.layout.state.setting_workspace_state(
                self.workspace, self.layout.state.get_workspace_state(self.workspace).replacing_view_state(
                    self.view,
                    i=i, j=j, w=w, h=h,
                    scale_origin=None, move_origin=None
                ).focusing_view(self.view))
            for h, (si, sj) in self._shoves.items():
                if h in self.layout._views:
                    state.update_view_state(self.layout._views[h], i=si, j=sj)
            state.validate_stack_indices(self.view)
            return state, conf_anim_t()
        except Exception:
            logger.warn("Unexpected: Error accessing view %s state", self.view)
            return None, 0
