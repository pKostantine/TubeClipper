"""Give the app the real macOS Window menu.

AppKit fills in Fill, Center, Move & Resize, Full Screen Tile, Bring All
to Front, the window list and the rest, keeps them in step with the OS
(fn+Control+F included), but only for the menu registered as the
application's Windows menu.  Qt never registers one, so a Qt app's Window
menu is a plain menu and fn+Control+F does nothing.  This finds the native
menu Qt built for our "Window" QMenu and registers it.

Talks to the Objective-C runtime through ctypes, so it needs no extra
packages.  It is best effort: if anything is missing the app keeps working
with a plain menu.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

_lib = None
P = ctypes.c_void_p


def _objc():
    global _lib
    if _lib is None:
        _lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        _lib.objc_getClass.restype = P
        _lib.objc_getClass.argtypes = [ctypes.c_char_p]
        _lib.sel_registerName.restype = P
        _lib.sel_registerName.argtypes = [ctypes.c_char_p]
    return _lib


def _sel(name):
    return _objc().sel_registerName(name.encode())


def _cls(name):
    return _objc().objc_getClass(name.encode())


def _msg(restype, argtypes, obj, selector, *args):
    """objc_msgSend with its own prototype, so calls cannot clobber each other."""
    lib = _objc()
    proto = ctypes.CFUNCTYPE(restype, P, P, *argtypes)
    fn = proto(ctypes.cast(lib.objc_msgSend, P).value)
    return fn(obj, _sel(selector), *args)


def _str(text):
    return _msg(P, [ctypes.c_char_p], _cls("NSString"),
                "stringWithUTF8String:", text.encode("utf-8"))


def _py(nsstring):
    if not nsstring:
        return ""
    raw = _msg(ctypes.c_char_p, [], nsstring, "UTF8String")
    return raw.decode("utf-8") if raw else ""


def _titles(menu):
    count = _msg(ctypes.c_long, [], menu, "numberOfItems")
    return [_py(_msg(P, [], _msg(P, [ctypes.c_long], menu, "itemAtIndex:", i),
                     "title"))
            for i in range(count)]


def _insert(menu, title, action, key, index):
    item = _msg(P, [], _cls("NSMenuItem"), "alloc")
    item = _msg(P, [P, P, P], item, "initWithTitle:action:keyEquivalent:",
                _str(title), _sel(action), _str(key))
    _msg(None, [P, ctypes.c_long], menu, "insertItem:atIndex:", item, index)


def _window_item(title):
    app = _msg(P, [], _cls("NSApplication"), "sharedApplication")
    main = _msg(P, [], app, "mainMenu")
    if not main:
        return app, None
    return app, _msg(P, [P], main, "itemWithTitle:", _str(title))


def _window_menu(title):
    app, item = _window_item(title)
    return app, (_msg(P, [], item, "submenu") if item else None)


def install_window_menu(title="Window"):
    """Register the native menu titled ``title`` as the Windows menu.

    Returns the item titles it ends up with, or None when this is not macOS
    or the menu could not be found.
    """
    if sys.platform != "darwin":
        return None
    try:
        app, item = _window_item(title)
        menu = _msg(P, [], item, "submenu") if item else None
        if not menu:
            return None
        # Qt hides a menu with no Qt actions in it, and this one has none:
        # everything in it comes from AppKit.
        _msg(None, [ctypes.c_bool], item, "setHidden:", False)
        _msg(None, [ctypes.c_bool], item, "setEnabled:", True)
        _msg(None, [ctypes.c_bool], menu, "setAutoenablesItems:", True)
        existing = _titles(menu)
        # Minimize and Zoom must be AppKit's own actions: AppKit places Fill,
        # Center and the rest relative to them.
        if "Zoom" not in existing:
            _insert(menu, "Zoom", "performZoom:", "", 0)
        if "Minimize" not in existing:
            _insert(menu, "Minimize", "performMiniaturize:", "m", 0)
        if "Bring All to Front" not in existing:
            count = _msg(ctypes.c_long, [], menu, "numberOfItems")
            separator = _msg(P, [], _cls("NSMenuItem"), "separatorItem")
            _msg(None, [P, ctypes.c_long], menu, "insertItem:atIndex:",
                 separator, count)
            _insert(menu, "Bring All to Front", "arrangeInFront:", "", count + 1)
        _msg(None, [P], app, "setWindowsMenu:", menu)
        return _titles(menu)
    except Exception as exc:          # pragma: no cover - diagnostics only
        print(f"Window menu not installed: {exc!r}", file=sys.stderr)
        return None


def window_menu_titles(title="Window"):
    """What the Window menu holds right now (macOS only)."""
    if sys.platform != "darwin":
        return None
    _app, menu = _window_menu(title)
    return _titles(menu) if menu else None
