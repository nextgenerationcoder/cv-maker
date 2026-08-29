from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

import settings_store
from auth import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UpdateSettingsRequest(BaseModel):
    llm_provider: str
    api_key: Optional[str] = None  # None = leave unchanged, "" = clear

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in settings_store.VALID_PROVIDERS:
            raise ValueError(f"Unknown provider: {v}. Must be one of {sorted(settings_store.VALID_PROVIDERS)}.")
        return v


def _masked_preview(user_id: str) -> Optional[str]:
    key = settings_store.get_decrypted_api_key(user_id)
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}{'•' * 6}{key[-4:]}"


@router.get("")
def get_settings(current_user: dict = Depends(get_current_user)):
    settings = settings_store.get_settings(current_user["id"])
    provider = settings["llm_provider"] if settings else "anthropic"
    preview = _masked_preview(current_user["id"])
    return {
        "llm_provider": provider,
        "has_api_key": preview is not None,
        "api_key_preview": preview,
        "available_providers": sorted(settings_store.VALID_PROVIDERS),
    }


@router.put("")
def update_settings(body: UpdateSettingsRequest, current_user: dict = Depends(get_current_user)):
    try:
        settings_store.upsert_settings(current_user["id"], body.llm_provider, body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    settings = settings_store.get_settings(current_user["id"])
    preview = _masked_preview(current_user["id"])
    return {
        "llm_provider": settings["llm_provider"],
        "has_api_key": preview is not None,
        "api_key_preview": preview,
        "available_providers": sorted(settings_store.VALID_PROVIDERS),
    }
