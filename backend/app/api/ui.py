"""Durable UI preferences (currently just the light/dark theme choice).

These live server-side because the packaged desktop app runs the backend on a fresh
localhost port every launch, which changes the webview's origin and wipes its
localStorage. The backend also injects the stored theme into the served index.html so
the page paints the right theme with no flash (see app/main.py)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..settings_store import get_ui_pref, set_ui_pref

router = APIRouter(prefix="/api/ui", tags=["ui"])

THEME_KEY = "theme"
VALID_THEMES = {"auto", "light", "dark"}


class UiPrefs(BaseModel):
    theme: str = "auto"


@router.get("/preferences", response_model=UiPrefs)
def get_preferences() -> UiPrefs:
    return UiPrefs(theme=get_ui_pref(THEME_KEY, "auto"))


@router.put("/preferences", response_model=UiPrefs)
def update_preferences(payload: UiPrefs) -> UiPrefs:
    if payload.theme not in VALID_THEMES:
        raise HTTPException(400, f"theme must be one of {sorted(VALID_THEMES)}")
    set_ui_pref(THEME_KEY, payload.theme)
    return UiPrefs(theme=payload.theme)
