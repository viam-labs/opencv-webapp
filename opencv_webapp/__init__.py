"""
OpenCV Calibration WebApp Module.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from .webapp import WebApp

__all__ = ["WebApp"]


def __getattr__(name: str):
    if name == "WebApp":
        from .webapp import WebApp

        return WebApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

