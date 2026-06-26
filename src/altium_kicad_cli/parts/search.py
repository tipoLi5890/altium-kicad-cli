"""jlcsearch (tscircuit) HTTP client — the ONLY networked module in this package.

Everything else in ``altium-kicad-cli`` is strictly offline. This module talks to
the public **jlcsearch** service (https://jlcsearch.tscircuit.com), tscircuit's
open-source (MIT) search front end over the JLCPCB / LCSC component database
(``jlcparts`` data). It is import-isolated under ``altium_kicad_cli.parts`` and is
loaded **lazily** by the ``jlc`` CLI subcommand only, so the rest of the CLI stays
zero-network / zero-dependency.

Transport is **stdlib ``urllib`` only**. Every request goes through an injectable
``opener`` (any object exposing ``open(request, *, timeout=...)``, i.e. an
``urllib.request.OpenerDirector``), so tests run fully offline with a mocked
transport. Network/HTTP failures are mapped to :class:`JlcNetworkError` — a raw
traceback never escapes (the CLI surfaces a clean ``ERROR: NETWORK: …`` line and
the external-tool exit code).

Endpoints (researched against the live service)
-----------------------------------------------
* General keyword search:  ``GET /components/list.json?search=<q>&limit=<n>``
  → ``{"components": [ {lcsc, mfr, package, description, stock, price,
  category, subcategory, is_basic, is_preferred}, ... ]}``.
  ``search`` matches MPN, category and the LCSC C-number (with or without the
  ``C`` prefix). An empty result set is ``{"components": []}``.
* Fetch one part: there is no by-id route, so :func:`get` searches the C-number
  and returns the exact ``lcsc`` match.

``price`` arrives as a JSON-encoded **string** of quantity tiers
(``[{"qFrom":1,"qTo":49,"price":0.091}, ...]``); :class:`Part` exposes the
lowest-quantity unit price as a float plus the full tier list under
``attributes["price_tiers"]``.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import __version__

# --- service + transport constants ------------------------------------------
BASE_URL = "https://jlcsearch.tscircuit.com"
SEARCH_PATH = "/components/list.json"
USER_AGENT = (
    f"altium-kicad-cli/{__version__} "
    "(+https://github.com/tipoLi5890/altium-kicad-cli; jlcsearch client)"
)
DEFAULT_TIMEOUT = 15.0            # seconds; bounded so a hung service can't wedge the CLI
DEFAULT_LIMIT = 20
MAX_RESPONSE_BYTES = 16 * 1024 * 1024   # hard cap on a single response body
CACHE_TTL_SECONDS = 3600          # on-disk cache freshness window


class JlcNetworkError(Exception):
    """A jlcsearch request failed.

    Covers an unreachable host, a timeout, a non-2xx HTTP status, an oversized
    body, or undecodable JSON. Carries a clean human-readable ``message``; the CLI
    maps this onto the external-tool exit code and never leaks a traceback.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class Part:
    """One normalized jlcsearch / LCSC component result."""

    lcsc: str                 # display C-number, e.g. "C7593"
    mpn: str                  # manufacturer part number (jlcsearch "mfr")
    description: str
    package: str
    stock: int
    price: float | None       # representative unit price (lowest-quantity tier)
    basic: bool               # JLCPCB "Basic" part (is_basic)
    datasheet: str | None
    category: str
    attributes: dict = field(default_factory=dict)  # subcategory, is_preferred, price_tiers, specs

    @property
    def preferred(self) -> bool:
        return bool(self.attributes.get("is_preferred"))

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# helpers (pure / offline)
# --------------------------------------------------------------------------- #
def _lcsc_digits(value: object) -> str:
    """Strip a leading ``C`` and surrounding whitespace → the bare digits."""
    s = str(value or "").strip().upper()
    if s.startswith("C"):
        s = s[1:]
    return s


def _display_lcsc(value: object) -> str:
    digits = _lcsc_digits(value)
    return ("C" + digits) if digits else ""


def _parse_price(raw: object) -> tuple[float | None, list[dict]]:
    """Return ``(unit_price, tiers)`` from jlcsearch's price field.

    The field is usually a JSON-encoded string of quantity tiers; it may also be a
    bare number (``price1`` style) or already-decoded list. The representative unit
    price is the price of the lowest-``qFrom`` tier.
    """
    if raw is None:
        return None, []
    tiers: object = raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, []
        try:
            tiers = json.loads(s)
        except (ValueError, TypeError):
            try:
                return float(s), []
            except (ValueError, TypeError):
                return None, []
    if isinstance(tiers, (int, float)):
        return float(tiers), []
    if isinstance(tiers, list):
        norm: list[dict] = []
        for t in tiers:
            if not isinstance(t, dict) or "price" not in t:
                continue
            try:
                norm.append(
                    {"qFrom": t.get("qFrom"), "qTo": t.get("qTo"), "price": float(t["price"])}
                )
            except (ValueError, TypeError):
                continue
        if not norm:
            return None, []
        cheapest_first = min(
            norm, key=lambda t: (t["qFrom"] if isinstance(t["qFrom"], (int, float)) else 0)
        )
        return cheapest_first["price"], norm
    return None, []


def _to_part(d: dict) -> Part:
    """Map one raw jlcsearch component object onto a :class:`Part`."""
    price_raw = d.get("price")
    if price_raw is None:
        price_raw = d.get("price1")
    unit_price, tiers = _parse_price(price_raw)

    attrs: dict = {}
    if d.get("subcategory") is not None:
        attrs["subcategory"] = d["subcategory"]
    if d.get("is_preferred") is not None:
        attrs["is_preferred"] = bool(d["is_preferred"])
    if tiers:
        attrs["price_tiers"] = tiers
    raw_specs = d.get("attributes")
    if isinstance(raw_specs, str) and raw_specs.strip():
        try:
            parsed = json.loads(raw_specs)
            if isinstance(parsed, dict):
                attrs["specs"] = parsed
        except (ValueError, TypeError):
            pass
    elif isinstance(raw_specs, dict):
        attrs["specs"] = raw_specs

    try:
        stock = int(d.get("stock") or 0)
    except (ValueError, TypeError):
        stock = 0

    datasheet = d.get("datasheet")
    return Part(
        lcsc=_display_lcsc(d.get("lcsc")),
        mpn=str(d.get("mfr") or d.get("mpn") or ""),
        description=str(d.get("description") or ""),
        package=str(d.get("package") or ""),
        stock=stock,
        price=unit_price,
        basic=bool(d.get("is_basic")),
        datasheet=(str(datasheet) if datasheet else None),
        category=str(d.get("category") or ""),
        attributes=attrs,
    )


def _extract_rows(payload: object) -> list:
    """Pull the result array out of a jlcsearch response (key is page-specific)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("components", "results", "parts"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
        for v in payload.values():        # any list-valued key (e.g. "resistors")
            if isinstance(v, list):
                return v
    return []


def _build_url(params: dict) -> str:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return f"{BASE_URL}{SEARCH_PATH}?{qs}"


def _default_opener() -> urllib.request.OpenerDirector:
    """Build the real urllib opener. Tests monkeypatch this to inject a fake."""
    return urllib.request.build_opener()


# --------------------------------------------------------------------------- #
# on-disk cache (optional)
# --------------------------------------------------------------------------- #
def _cache_path(cache_dir: str | Path, url: str) -> Path:
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return Path(cache_dir) / f"jlc_{key}.json"


def _cache_read(cache_dir: str | Path | None, url: str, ttl: float | None) -> object | None:
    if not cache_dir:
        return None
    p = _cache_path(cache_dir, url)
    try:
        st = p.stat()
    except OSError:
        return None
    if ttl is not None and (time.time() - st.st_mtime) > ttl:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_write(cache_dir: str | Path | None, url: str, payload: object) -> None:
    if not cache_dir:
        return
    try:
        d = Path(cache_dir)
        d.mkdir(parents=True, exist_ok=True)
        _cache_path(cache_dir, url).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # cache is best-effort; never fail a query because of it


# --------------------------------------------------------------------------- #
# transport
# --------------------------------------------------------------------------- #
def _fetch_json(url: str, *, opener: urllib.request.OpenerDirector, timeout: float) -> object:
    """GET ``url`` and decode JSON, mapping every failure to :class:`JlcNetworkError`."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:      # subclass of URLError — must come first
        reason = getattr(e, "reason", "") or ""
        raise JlcNetworkError(f"jlcsearch returned HTTP {e.code} {reason}".strip()) from e
    except urllib.error.URLError as e:
        raise JlcNetworkError(f"could not reach jlcsearch: {getattr(e, 'reason', e)}") from e
    except TimeoutError as e:                # socket.timeout is an alias since 3.10
        raise JlcNetworkError(f"jlcsearch request timed out after {timeout}s") from e

    try:
        raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, urllib.error.URLError) as e:
        raise JlcNetworkError(f"jlcsearch read failed: {e}") from e
    finally:
        close = getattr(resp, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover - defensive
                pass

    if len(raw) > MAX_RESPONSE_BYTES:
        raise JlcNetworkError("jlcsearch response exceeded the size cap")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise JlcNetworkError(f"jlcsearch returned invalid JSON: {e}") from e


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def search(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    opener: urllib.request.OpenerDirector | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    cache_dir: str | Path | None = None,
    cache_ttl: float | None = CACHE_TTL_SECONDS,
) -> list[Part]:
    """Keyword-search jlcsearch and return up to ``limit`` :class:`Part` results.

    ``query`` matches MPN, category and the LCSC C-number. ``opener`` injects a
    transport (defaults to a real urllib opener) so tests run offline. Pass
    ``cache_dir`` to enable a short on-disk cache keyed by request URL.
    """
    if opener is None:
        opener = _default_opener()
    try:
        lim = max(1, int(limit))
    except (ValueError, TypeError):
        lim = DEFAULT_LIMIT

    url = _build_url({"search": query, "limit": lim})
    payload = _cache_read(cache_dir, url, cache_ttl)
    if payload is None:
        payload = _fetch_json(url, opener=opener, timeout=timeout)
        _cache_write(cache_dir, url, payload)

    parts = [_to_part(r) for r in _extract_rows(payload) if isinstance(r, dict)]
    return parts[:lim]


def get(
    lcsc_id: str,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    cache_dir: str | Path | None = None,
    cache_ttl: float | None = CACHE_TTL_SECONDS,
) -> Part | None:
    """Fetch one part by LCSC C-number (``"C7593"`` or ``"7593"``); ``None`` if absent."""
    digits = _lcsc_digits(lcsc_id)
    if not digits:
        return None
    results = search(
        "C" + digits,
        limit=DEFAULT_LIMIT,
        opener=opener,
        timeout=timeout,
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
    )
    for p in results:
        if _lcsc_digits(p.lcsc) == digits:
            return p
    return None
