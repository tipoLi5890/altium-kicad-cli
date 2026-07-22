"""`akcli view` — the local web dashboard (calculators + live schematic watch).

``view`` / ``view calc`` / ``view live [sch]`` / ``view <sch.kicad_sch>`` all
serve from one localhost server: /calc always, /live when a schematic is
watched. Bare ``view`` needs no file — it serves the hub with /live idle;
``view live`` without a path watches the only ``.kicad_sch`` in the current
directory. Heavy imports stay LAZY per handler.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..errors import EXIT
from ._shared import _ExitWith, _require_path

_DISCOVER_LIST_MAX = 8   # candidates named in the ambiguous-discovery error


def _discover_sch() -> Path:
    """The single ``.kicad_sch`` in the current directory, or a USAGE error.

    Zero candidates points at bare ``view`` (the hub needs no file); more
    than one demands an explicit choice — auto-picking among sheets of a
    hierarchical design would silently watch the wrong one.
    """
    cands = sorted(Path.cwd().glob("*.kicad_sch"))
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise _ExitWith(
            EXIT["USAGE"],
            "ERROR: view live: no .kicad_sch in the current directory — "
            "pass a path, or run bare `akcli view` for the hub")
    names = ", ".join(p.name for p in cands[:_DISCOVER_LIST_MAX])
    if len(cands) > _DISCOVER_LIST_MAX:
        names += ", …"
    raise _ExitWith(
        EXIT["USAGE"],
        f"ERROR: view live: multiple .kicad_sch here ({names}) — "
        "pass the one to watch")


def _cmd_view(args: argparse.Namespace) -> int:
    """`view` / `view calc` / `view live [sch]` / `view <sch>` — the dashboard.

    One server hosts both pages: /calc always, /live when a schematic is
    watched. Bare `view` serves the hub unwatched; `view <sch.kicad_sch>` is
    shorthand for `view live <sch>`; `view live` alone auto-discovers the
    single .kicad_sch in the current directory.
    """
    from ..webui import server

    what, path = args.what, args.path
    if what and what.lower().endswith(".kicad_sch") and not path:
        what, path = "live", what
    port = args.port if args.port is not None else server.DEFAULT_PORT
    if what is None or what == "calc":
        return server.serve(port=port, open_browser=not args.no_browser,
                            max_steps=args.max_steps)
    if what != "live":
        raise _ExitWith(EXIT["USAGE"],
                        "ERROR: view expects no argument (hub), `calc`, "
                        "`live [sch]`, or a .kicad_sch path")
    target = _discover_sch() if path is None else _require_path(
        path, "schematic to watch")
    if not str(target).lower().endswith(".kicad_sch"):
        raise _ExitWith(EXIT["USAGE"], "ERROR: view live watches a .kicad_sch")
    return server.serve(port=port, open_browser=not args.no_browser,
                        target=target, state_dir=args.state_dir,
                        max_steps=args.max_steps)


def register(sub, common) -> None:
    p = sub.add_parser("view", parents=[common],
                       help="local web dashboard: /calc (calculators) + /live "
                            "(watch a .kicad_sch); bare `view` serves the hub")
    p.add_argument("what", nargs="?",
                   help="`calc`, `live [sch]`, or directly a .kicad_sch to "
                        "watch; omit to serve the hub with nothing watched")
    p.add_argument("path", nargs="?",
                   help="the .kicad_sch to watch (view live only; omitted -> "
                        "the single .kicad_sch in the current directory)")
    p.add_argument("--port", type=int,
                   help="listen port (default 8765; auto-increments if busy; "
                        "localhost only)")
    p.add_argument("--no-browser", action="store_true",
                   help="do not open the browser automatically")
    p.add_argument("--state-dir", metavar="DIR",
                   help="view live: persist the step timeline here "
                            "(default: fresh temp dir per run)")
    p.add_argument("--max-steps", type=int, default=500, metavar="N",
                   help="keep at most N timeline steps, deleting the oldest "
                        "SVGs (default 500; 0 = unlimited)")
    p.set_defaults(handler=_cmd_view)
