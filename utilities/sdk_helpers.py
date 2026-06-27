"""
sdk_helpers.py
--------------
Shared helper utilities for the EVE-NG MCP service and controller layers.

Helpers
-------
normalise_response(result)
    Coerce any SDK return value into a plain ``dict``.

wrap_errors(fn, *args, **kwargs)
    Call a service function and convert any exception into
    ``{"error": "..."}`` so MCP tools always return JSON-safe dicts.
    Used by the controller layer.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

_logger = logging.getLogger("eve_mcp")


# ---------------------------------------------------------------------------
# normalise_response
# ---------------------------------------------------------------------------

def normalise_response(result: Any) -> Dict:
    """Coerce an SDK response into a plain ``dict``.

    - ``dict``  → returned as-is
    - anything else → ``{"result": value}``
    """
    if isinstance(result, dict):
        return result
    return {"result": result}


# ---------------------------------------------------------------------------
# wrap_errors
# ---------------------------------------------------------------------------

def wrap_errors(fn: Callable, *args, **kwargs) -> Dict[str, Any]:
    """Call a service function and convert any exception to an error dict.

    Ensures that MCP tool handlers always return a JSON-serialisable dict
    rather than propagating raw Python exceptions to the client::

        # in eve_ng_controller.py
        return wrap_errors(svc.get_node, path, node_id)

    :param fn:     Service function to call.
    :param args:   Positional arguments forwarded to *fn*.
    :param kwargs: Keyword arguments forwarded to *fn*.
    :returns:      The function's return value, or ``{"error": "<message>"}``
                   if an exception is raised.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("wrap_errors caught %s: %s", type(exc).__name__, exc)
        return {"error": str(exc)}
