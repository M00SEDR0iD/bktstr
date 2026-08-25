from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status


def require_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Require the configured service bearer key without echoing it back."""
    configured_key = os.getenv("BKTSTR_API_KEY")
    scheme, _, supplied_key = (authorization or "").partition(" ")
    authorized = bool(configured_key) and scheme.lower() == "bearer" and secrets.compare_digest(
        supplied_key, configured_key
    )
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "A valid bearer API key is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
