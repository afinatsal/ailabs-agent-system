"""AI Labs Dashboard — FastAPI web UI.

Gunakan lewat `ailabs serve` atau langsung: `uvicorn ailabs.dashboard:app`.
"""

from ailabs.dashboard.app import app

__all__ = ["app"]
