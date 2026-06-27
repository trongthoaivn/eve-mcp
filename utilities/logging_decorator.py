"""
logging_decorator.py
--------------------
Reusable logging decorator for EVE-NG MCP service / controller functions.

Features
--------
- Logs function name, arguments, return value, execution time, and errors.
- Masks sensitive parameter values (password, token, secret, ...) automatically.
- Supports both sync and async functions transparently.
- Configurable log level per call-site.
- Emits structured log records via a dedicated ``eve_mcp`` logger so the
  output can be captured / filtered independently of the root logger.

Usage
-----
    from utilities.logging_decorator import log_call

    @log_call                          # default INFO level
    def my_function(path, node_id):
        ...

    @log_call(level=logging.DEBUG)     # explicit level
    async def my_async_function(...):
        ...

Log format (stderr by default)
-------------------------------
    2024-01-15 10:23:45,123 | INFO  | eve_mcp | CALL  get_server_status()
    2024-01-15 10:23:45,456 | INFO  | eve_mcp | OK    get_server_status -> {'status': 'running'} (0.333s)

    2024-01-15 10:23:50,100 | ERROR | eve_mcp | ERROR start_node(path='/lab/test', node_id=3) -> ConnectionError: ... (0.012s)
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import time
from typing import Any, Callable, Set

# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------

_logger = logging.getLogger("eve_mcp")

# Install a default handler only when the logger has no handlers yet, so
# any application-level logging config always takes precedence.
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    _logger.addHandler(_handler)
    _logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Sensitive parameter names (case-insensitive substring match)
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS: Set[str] = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "credential",
}


def _mask(key: str, value: Any) -> Any:
    """Return ``'***'`` if *key* contains a sensitive keyword, else *value*."""
    key_lower = key.lower()
    if any(s in key_lower for s in _SENSITIVE_KEYS):
        return "***"
    return value


def _safe_repr(value: Any, max_len: int = 200) -> str:
    """Return a compact, safe string representation of *value*."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = repr(value)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def _build_call_signature(fn: Callable, args: tuple, kwargs: dict) -> str:
    """Build a human-readable ``fn(param=value, ...)`` string with masking."""
    try:
        sig = inspect.signature(fn)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        parts = [
            f"{k}={_safe_repr(_mask(k, v))}"
            for k, v in bound.arguments.items()
        ]
    except (TypeError, ValueError):
        parts = [_safe_repr(a) for a in args] + [
            f"{k}={_safe_repr(_mask(k, v))}" for k, v in kwargs.items()
        ]
    return f"{fn.__name__}({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Core decorator
# ---------------------------------------------------------------------------

def log_call(
    fn: Callable | None = None,
    *,
    level: int = logging.INFO,
    log_result: bool = True,
    log_args: bool = True,
) -> Callable:
    """Decorator that logs entry, exit (with result), and errors of a function.

    Can be used with or without arguments::

        @log_call
        def foo(): ...

        @log_call(level=logging.DEBUG, log_result=False)
        def bar(): ...

    Parameters
    ----------
    fn:
        The decorated function (set automatically when used bare, i.e. ``@log_call``).
    level:
        Python logging level for CALL / OK messages (default: ``logging.INFO``).
        Errors are always logged at ``logging.ERROR``.
    log_result:
        Whether to include the return value in the OK log line (default: True).
    log_args:
        Whether to include function arguments in the CALL log line (default: True).
    """

    def decorator(func: Callable) -> Callable:

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                call_str = (
                    _build_call_signature(func, args, kwargs)
                    if log_args
                    else func.__name__ + "(...)"
                )
                _logger.log(level, "CALL  %s", call_str)
                t0 = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    elapsed = time.perf_counter() - t0
                    if log_result:
                        _logger.log(level, "OK    %s -> %s (%.3fs)", func.__name__, _safe_repr(result), elapsed)
                    else:
                        _logger.log(level, "OK    %s (%.3fs)", func.__name__, elapsed)
                    return result
                except Exception as exc:
                    elapsed = time.perf_counter() - t0
                    _logger.error("ERROR %s -> %s: %s (%.3fs)", call_str, type(exc).__name__, exc, elapsed)
                    raise

            return async_wrapper

        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                call_str = (
                    _build_call_signature(func, args, kwargs)
                    if log_args
                    else func.__name__ + "(...)"
                )
                _logger.log(level, "CALL  %s", call_str)
                t0 = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.perf_counter() - t0
                    if log_result:
                        _logger.log(level, "OK    %s -> %s (%.3fs)", func.__name__, _safe_repr(result), elapsed)
                    else:
                        _logger.log(level, "OK    %s (%.3fs)", func.__name__, elapsed)
                    return result
                except Exception as exc:
                    elapsed = time.perf_counter() - t0
                    _logger.error("ERROR %s -> %s: %s (%.3fs)", call_str, type(exc).__name__, exc, elapsed)
                    raise

            return sync_wrapper

    # Support both @log_call and @log_call(...)
    if fn is not None:
        return decorator(fn)
    return decorator


# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------

log_call_debug = functools.partial(log_call, level=logging.DEBUG)
"""Same as ``@log_call`` but defaults to DEBUG level."""

log_call_warning = functools.partial(log_call, level=logging.WARNING)
"""Same as ``@log_call`` but defaults to WARNING level."""
