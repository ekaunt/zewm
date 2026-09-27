# zewm

zewm is a personal fork of [newm-next](https://github.com/newm-next/newm-next). The Python package and code identifiers are unchanged. The commands and config location are renamed:

| newm-next | zewm |
|---|---|
| `start-newm` | `zewm` |
| `newm-cmd`, `newmctl` | `zewm-cmd`, `zewmctl` |
| `newm-panel-basic` | `zewm-panel-basic` |
| `~/.config/newm/`, `/etc/newm/` | `~/.config/zewm/`, `/etc/zewm/` |
| `~/.cache/newm/newm_log` | `~/.cache/zewm/zewm_log` |

## Changes from newm-next

All new behavior is behind config keys and off by default, except where noted.

### Zoom

- **Content scales when zoomed out** (`view.scale_content_on_zoom`). Past the given zoom level, windows stop being resized and are drawn smaller instead, so zooming out shows more desktop rather than reflowing apps. `2` keeps upstream reflow up to a 2x2 view and scales beyond it. `True` scales at every zoom level.
- **Zoom centers on the focused window** for both the `basic_scale` keybindings and the 4-finger swipe, instead of anchoring the top-left corner. Always on.
- **Zoom remembers the view per level.** Zooming back out returns to the position last used at that zoom level, unless the focused window would be off screen there. Always on.

### Placing and moving windows

- **Preselect a tile** (`layout.enter_preselect()`). A red outline marks a free tile. hjkl or the arrow keys jump between free tiles, the mouse hovers them, and Return, Space or a click confirms. The next new window opens there. Escape, or the binding again (also while the outline is pending), clears it. Look is set by `preselect.color` and `preselect.width`.
- **Mod+drag follows the pointer** (`move_resize.follow_cursor`). The window moves 1:1 with the cursor, without lowpass lag or tile stickiness, and drops when the modifier is released. The drop target is outlined, and windows that would be shoved slide there live as a preview. The preview slide and the drop use the same linear `anim_time` timing as other layout animations.
  - Center of another window: tab onto it (matching its size).
  - Edge of another window (`move_resize.shove_edge`, default `0.25`): take its place and push it, and anything it bumps into, toward that edge.
  - Empty space: snap to the nearest tile.
- **Keyboard move swaps** (`move.swap`). `move_focused_view` trades places with the windows in the way instead of stacking onto them.
- **Keyboard resize shoves** (`resize.shove`). `resize_focused_view` pushes the windows a growing edge runs into instead of overlapping them. This also fixes stack indices being validated against the pre-resize state.

### Focus

- **Mouse follows focus** (`focus.mouse_follows_focus`). When focus changes, by keyboard or because a new window opened, the cursor moves to the center of the newly focused window once the view has settled. It stays put if it is already over that window.

### Example

```python
view = {'scale_content_on_zoom': 2}
move_resize = {'gesture_factor': 1, 'follow_cursor': True}
move = {'grid_m': 1, 'swap': True}
resize = {'shove': True}
focus = {'mouse_follows_focus': True}
swipe_zoom = {'gesture_factor': -4}  # flip 4-finger zoom direction

def key_bindings(layout):
    return [
        ("L-a", lambda: layout.enter_preselect()),
        # ...
    ]
```

## Install on Arch Linux

A PKGBUILD for `zewm-git` is in [pkg/arch](pkg/arch). It builds pywm-next with the wlroots fix below applied:

```sh
git clone https://github.com/ekaunt/zewm
cd zewm/pkg/arch
makepkg -si
```

It conflicts with the other newm packages because it installs the same Python packages.

## Building pywm-next against current libinput

zewm uses upstream [pywm-next](https://github.com/newm-next/pywm-next) unchanged. Its bundled wlroots does not handle the switch types newer libinput added, so the build may fail in `backend/libinput/switch.c`. Add a `default` case to the switch-type `switch` in `handle_switch_toggle` in `subprojects/wlroots/backend/libinput/switch.c`:

```c
	case LIBINPUT_SWITCH_TABLET_MODE:
		wlr_event.switch_type = WLR_SWITCH_TYPE_TABLET_MODE;
		break;
	default:
		return;
	}
```

---

# newm-next (upstream README)

## Annoucment

Come talk to us on [discord](https://discord.gg/GnCsYRWtBq)!

[video couteresy of Audrick Yeu](https://www.youtube.com/watch?v=IkriZGyjoeU), used with permission.

## Current state

Unfortunately, the orignal author of newm, jbuchermn no longer has the time to maintain this project.

I have been contributing to this project( @Pandademic on github, if you need proof), and have decided to fork it here for the sake of keeping it alive and maintained.

This IS a fork, and is reflected as such in [./LICENSE](./LICENSE)


## Idea

**newm-next** is a Wayland compositor written with laptops and touchpads in mind. The idea is, instead of placing windows inside the small viewport (that is, the monitor) to arrange them along an arbitrarily large two-dimensional wall (generally without windows overlapping) and focus the compositors job on moving around along this wall efficiently and providing ways to the user to rearrange the wall such that they find the overall layout intuitive.

So, windows are placed on a two-dimensional grid of tiles taking either one by one, one by two, two by one, ... tiles of that grid. The compositor shows a one by one, two by two, ... view of that grid but scales the windows so they are usable on any zoom level (that is, zooming out the compositor actually changes the windows sizes). This makes for example switching between a couple of fullscreen applications very easy - place them in adjacent one by one tiles and have the compositor show a one by one view. And if you need to see them in parallel, zoom out. Then back in, and so on...

The basic commands therefore are navigation (left, right, top, bottom) and zoom-in and -out. These commands can be handled very intuitively on the touchpad (one- and two-finger gestures are reserved for interacting with the apps):

- Use three fingers to move around the wall
- Use four fingers to zoom out (move them upward) or in (downward)

To be able to arrange the windows in a useful manner, use

- `Logo` (default , unless configured otherwise) + one finger on the touchpad to move windows
- `Logo` (default , unless configured otherwise) + two fingers on the touchpad to change the extent of a window

To get a quick overview of all windows, just hit the `Logo` (default , unless configured otherwise) key.
Additionally with a quick 5-finger swipe a launcher panel can be opened.

These behaviours can (partly) be configured (see below for setup). By default (check [default_config.py](newm/default_config.py)), the following key bindings (among others) are in place

- `Logo-hjkl`: Move around
- `Logo-un`: Scale
- `Logo-HJKL`: Move windows around
- `Logo-Ctrl-hjkl`: Resize windows
- `Logo-f`: Toggle a fullscreen view of the focused window (possibly resizing it)
- ...

## Roadmap

the current master branch is/was jbuchermn's 0.3 release, as a wip.

In honor of his efforts, the next release will be 0.4, built of from here.

Goals include:

- [ ] get the touchscreen patches to work with this version
- [x] hike to latest wlroots
- [ ] MAYBE: fix up/update build system
- [x] investigate various bugs that have been filed
- [x] get newm to build without having ugly wlroots errors sometimes.



## Installing

### Arch Linux

[Install on Arch linux](doc/install_Arch_Linux.md)

There is a AUR package, `newm-next-git`.

Someone told me that the PKGBUILD was faulty. It works but it needs some fixing.


### NixOS (NEEDS TO BE DONE, NOT WORKING)

flakes are probably the easiest way to do this.

```sh
nix build "github:newm-next/newm-next#newm-next"
./result/bin/zewm -d
```

Note that this probably does not work outside nixOS. To fix OpenGL issues on other
linux distros using nix as a (secondary) package manager, see
[nixGL](https://github.com/guibou/nixGL). 

Known issues
-------------

PAM authentication appears to be broken in this setup.

### Installing with pip

[pywm-next](https://github.com/newm-next/pywm-next) is the  main dependency of newm-next. If all prerequisites are installed, the command:

```sh
pip3 install --user git+https://github.com/newm-next/pywm-next
```

should suffice.Additionally, unless configured otherwise, newm-next uses alacritty as its default terminal.

To install newm:

```sh
pip3 install --user git+https://github.com/newm-next/newm-next
```

Installing newm this way means it cannot be used as a login manager, as it can only be started by your current user (see below)

### Usage

Start newm using

```sh
zewm -d
```

it will log to `$HOME/.cache/zewm/zewm_log`, if this file exists, it will move it to `$HOME/.cache/zewm/zewm_log.old.$year-$month-$day-$epoch`(the timestamps of its last edit)

you can use the `-d` flag for a more verbose, debug-y output.
you can use the `-c` flag to point it toward a config file.

## Configuration

### Setting up the config file and first example

Configuring is handled via Python and read from either `$HOME/.config/zewm/config.py` or (lower precedence) `/etc/zewm/config.py`. Take `default_config.py` as a basis; details on the possible keys are provided below.

The `default_config.py` file can be found in the [repo](newm/default_config.py) or on your computer at `/usr/lib/pythonX.XX/site-packages/newm/default_config.py`

Copy it to `$HOME/.config/zewm/config.py` and adjust, e.g. for a German HiDPI MacBook with a wallpaper placed in the home folder,

```py
import os
from pywm import (
    PYWM_MOD_LOGO,
    PYWM_MOD_ALT
)

def on_startup():
    os.system("waybar &")

def on_reconfigure():
    os.system("notify-send newm \"Reloaded configuration\" &")

bar = {
    'enabled': False,
}

background = {
    'path': os.environ['HOME'] + '/wallpaper.jpg'
}

outputs = [
    { 'name': 'eDP-1', 'scale': 2. }
]

pywm = {
    'xkb_model': "macintosh",
    'xkb_layout': "de,de",
    'xkb_options': "caps:escape",
}
```

### Configuring

The configuration works by evaluating the python config file and extracting the variables which the file exports. So basically you can do whatever you please to provide the configuration values,
hence why certain config elements are callbacks. Some elements are hierarchical, to set these use Python dicts - e.g. for `x.y`:

```py
x = {
    'y': 2.0
}
```

The configuration can be dynamically updated (apart from a couple of fixed keys) using `Layout.update_config` (by default bound to `Mod+C`).

See [config](./doc/config.md) for a documentation on all configurable values.

**BEWARE that functions (as in keybindings, `on_startup`, ...) are run synchronously in the compositor thread.**

### Troubleshooting: Touchpad

It is very much encouraged to use evdev, instead of python gestures (see [config](./doc/config.md)), however these might not work right from the start. Try:

```
ls -al /dev/input/event*
evtest
```

This is a required prerequisite to use the python-side (smoother) gestures. C-side or DBus gestures do not require this.

As a side note, this is not necessary for a Wayland compositor in general as the devices can be accessed through `systemd-logind` or `seatd` or similar.
However the python `evdev` module does not allow instantiation given a file descriptor (only a path which it then opens itself),
so usage of that module would no longer be possible in this case (plus at first sight there is no easy way of getting that file descriptor to the 
Python side). Also `wlroots` (`libinput` in the backend) does not expose touchpads as what they are (`touch-down`, `touch-up`, `touch-motion` for any
number of parallel slots), but only as pointers (`motion` / `axis`), so gesture detection around `libinput`-events is not possible as well.

Therefore, we're stuck with the less secure (and a lot easier) way of using the group (probably) named `input`.

## Next steps

- [Tips and tricks](./doc/tips_and_tricks.md)
- [Environment setup](./doc/env_wayland.md)
- [Systemd integration](./doc/systemd.md)
- [Look and feel](./doc/look_and_feel.md)

### Using zewm-cmd

`zewm-cmd` provides a way to interact with a running newm instance from command line:

- `zewm-cmd inhibit-idle` prevents newm from going into idle states (dimming the screen)
- `zewm-cmd config` reloads the configuration
- `zewm-cmd lock` locks the screen
- `zewm-cmd open-virtual-output <name>` opens a new virtual output (see [newm-sidecar](https://github.com/jbuchermn/newm-sidecar))
- `zewm-cmd close-virtual-output <name>` close a virtual output
- `zewm-cmd clean` removes orphaned states, which can happen, but shouldn't (if you encounter the need for this, please file a bug)
- `zewm-cmd debug` prints out some debug info on the current state of views
- `zewm-cmd unlock` unlocks the compositor (if explicitly enabled in config) - this is useful in case you have trouble setting up the lock screen.

### Logging straight into newm (greetd) 

Make sure to install newm-next as well as pywm-next and a newm panel in a way in which the `greeter` user has access.

Place newm-next configuration in `/etc/zewm/config.py` and check, after logging in as `greeter`, that `zewm` works and shows the login panel (login itself should not work). If it works, set

```toml
command = "zewm"
```

in `/etc/greetd/config.toml`.


## Credits

Thank you to:

- Jonas Bucher for starting newm
- Diego Aguilar for maintaing the atha AUR package and all the support and help you gave newm
- Audrick Yeu for the amazing insight on the project, countless amount of time spent on improving the experience of users, and for the lovely readme video!
- and all the other contributors to both newm, newm-atha and newm-next!
