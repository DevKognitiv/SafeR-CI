"""
SafeR CI — Users API

Placeholder router. There is no User model yet; these endpoints exist so the
app boots with a stable URL surface and can be filled in once auth lands.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/")
async def list_users():
    """No users are persisted yet."""
    return []


@router.get("/me")
async def current_user():
    raise HTTPException(status_code=501, detail="authentication not yet implemented")
