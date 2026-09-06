"""Scenes (tap-to-run) and automations routes.

Paths are declared in full (``/homes/{home_id}/scenes``, ``/scenes/{scene_id}``, ``/homes/{home_id}/automations``,
``/automations/{automation_id}``); the hub router mounts them under ``/api/v1/hub``. Membership is checked
through ``deps`` for every route: scenes and automations resolve to their home and the caller must be a member
(404 otherwise); creating / editing / deleting requires ``admin`` or ``owner``; running a scene or manually
triggering an automation is open to every member (like tapping a scene in the Tuya app).

Referential checks (400): every ``device_id`` used in actions, triggers and conditions must belong to the home,
``device_command`` codes must be writable capabilities of that device with an acceptable value, ``run_scene``
targets must be scenes of the same home and a scene cannot run itself. Action / trigger / condition *shapes*
are validated by the pydantic schemas (422).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub.automation.engine import run_automation
from app.hub.automation.runner import SceneRunner, scene_summary
from app.hub.capabilities import coerce_value, find_capability
from app.hub.deps import HomeAccess, get_current_user, get_db, home_access, load_home_access
from app.hub.models import Automation, Device, Scene, User
from app.hub.runtime import get_runtime
from app.hub.schemas import (
    AutomationIn, AutomationOut, AutomationUpdate, ReorderIn, SceneIn, SceneOut, SceneUpdate,
)

logger = logging.getLogger("safer.hub.routes.scenes")

router = APIRouter()

__all__ = ["router", "scene_to_out", "automation_to_out", "SceneRunOut", "AutomationTriggerOut"]


# ----------------------------------------------------------------------------- response models
class SceneRunOut(BaseModel):
    """Result of ``POST /scenes/{id}/run``: one entry per action, in order."""

    scene_id: str
    name: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)
    ran_at: Optional[datetime] = None


class AutomationTriggerOut(BaseModel):
    """Result of ``POST /automations/{id}/trigger``."""

    automation_id: str
    name: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)
    triggered_at: Optional[datetime] = None


# ----------------------------------------------------------------------------- helpers
def scene_to_out(scene: Scene) -> SceneOut:
    """API representation of a scene."""
    return SceneOut.model_validate(scene)


def automation_to_out(automation: Automation) -> AutomationOut:
    """API representation of an automation."""
    return AutomationOut.model_validate(automation)


def _clean_name(value: str, what: str) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{what} name is required")
    return name


async def _load_scene(scene_id: str, user: User, db: AsyncSession) -> Tuple[Scene, HomeAccess]:
    """Scene + the caller's access to its home (404 for unknown scenes or homes the caller is not in)."""
    scene = await db.get(Scene, scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    access = await load_home_access(scene.home_id, user, db)
    return scene, access


async def _load_automation(automation_id: str, user: User, db: AsyncSession) -> Tuple[Automation, HomeAccess]:
    """Automation + the caller's access to its home (404 when unknown / not a member)."""
    automation = await db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")
    access = await load_home_access(automation.home_id, user, db)
    return automation, access


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


async def _validate_refs(
    db: AsyncSession,
    home_id: str,
    actions: Iterable[Dict[str, Any]],
    triggers: Iterable[Dict[str, Any]] = (),
    conditions: Iterable[Dict[str, Any]] = (),
    self_scene_id: Optional[str] = None,
) -> None:
    """400 unless every referenced device / scene belongs to ``home_id`` and commands are executable."""
    actions = [a for a in actions if isinstance(a, dict)]
    device_ids = {str(a["device_id"]) for a in actions if a.get("type") == "device_command" and a.get("device_id")}
    for item in list(triggers) + list(conditions):
        if isinstance(item, dict) and item.get("type") == "device_state" and item.get("device_id"):
            device_ids.add(str(item["device_id"]))
    scene_ids = {str(a["scene_id"]) for a in actions if a.get("type") == "run_scene" and a.get("scene_id")}

    devices: Dict[str, Device] = {}
    if device_ids:
        rows = (
            await db.execute(select(Device).where(Device.id.in_(list(device_ids)), Device.home_id == home_id))
        ).scalars().all()
        devices = {device.id: device for device in rows}
        missing = sorted(device_ids - set(devices))
        if missing:
            raise _bad_request(f"Unknown device id(s) for this home: {', '.join(missing)}")
    for action in actions:
        if action.get("type") != "device_command":
            continue
        device = devices[str(action["device_id"])]
        capability = find_capability(device.capabilities or [], str(action.get("code")))
        if capability is None:
            raise _bad_request(f"{device.name}: unknown capability '{action.get('code')}'")
        if not capability.get("writable"):
            raise _bad_request(f"{device.name}: capability '{action.get('code')}' is read-only")
        try:
            coerce_value(capability, action.get("value"))
        except ValueError as exc:
            raise _bad_request(f"{device.name}: {exc}") from exc

    if self_scene_id and self_scene_id in scene_ids:
        raise _bad_request("A scene cannot run itself")
    if scene_ids:
        found = set(
            (await db.execute(select(Scene.id).where(Scene.id.in_(list(scene_ids)), Scene.home_id == home_id))).scalars().all()
        )
        missing = sorted(scene_ids - found)
        if missing:
            raise _bad_request(f"Unknown scene id(s) for this home: {', '.join(missing)}")


async def _scenes_of(db: AsyncSession, home_id: str) -> List[Scene]:
    rows = await db.execute(
        select(Scene).where(Scene.home_id == home_id).order_by(Scene.sort_order, Scene.created_at, Scene.name)
    )
    return list(rows.scalars().all())


# ----------------------------------------------------------------------------- scenes
@router.get("/homes/{home_id}/scenes", response_model=List[SceneOut])
async def list_scenes(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> List[SceneOut]:
    """Scenes of a home ordered by ``sort_order`` then creation date."""
    return [scene_to_out(scene) for scene in await _scenes_of(db, access.home.id)]


@router.post("/homes/{home_id}/scenes", response_model=SceneOut, status_code=status.HTTP_201_CREATED)
async def create_scene(body: SceneIn, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> SceneOut:
    """Create a scene at the end of the list (admin or owner). 400 when an action references a foreign device/scene."""
    access.require("admin")
    await _validate_refs(db, access.home.id, body.actions)
    last = (await db.execute(select(func.max(Scene.sort_order)).where(Scene.home_id == access.home.id))).scalar_one()
    scene = Scene(
        home_id=access.home.id, name=_clean_name(body.name, "Scene"), icon=body.icon, color=body.color,
        actions=list(body.actions), enabled=body.enabled, sort_order=(last if last is not None else -1) + 1,
    )
    db.add(scene)
    await db.commit()
    logger.info("Scene %s (%s) created in home %s by %s", scene.id, scene.name, access.home.id, access.user.id)
    return scene_to_out(scene)


@router.get("/scenes/{scene_id}", response_model=SceneOut)
async def get_scene(scene_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> SceneOut:
    """One scene (404 unless the caller is a member of its home)."""
    scene, _ = await _load_scene(scene_id, user, db)
    return scene_to_out(scene)


@router.patch("/scenes/{scene_id}", response_model=SceneOut)
async def update_scene(
    scene_id: str, body: SceneUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SceneOut:
    """Update name / icon / color / actions / enabled / sort_order (admin or owner)."""
    scene, access = await _load_scene(scene_id, user, db)
    access.require("admin")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"], "Scene")
    if changes.get("actions") is not None:
        await _validate_refs(db, scene.home_id, changes["actions"], self_scene_id=scene.id)
        changes["actions"] = list(changes["actions"])
    elif "actions" in changes:
        changes.pop("actions")  # explicit null: keep the current actions
    for field, value in changes.items():
        setattr(scene, field, value)
    await db.commit()
    logger.info("Scene %s updated by %s (%s)", scene.id, user.id, ", ".join(sorted(changes)) or "no changes")
    return scene_to_out(scene)


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_scene(scene_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Response:
    """Delete a scene (admin or owner). Other scenes/automations still pointing at it report ``not_found`` when run."""
    scene, access = await _load_scene(scene_id, user, db)
    access.require("admin")
    await db.delete(scene)
    await db.commit()
    logger.info("Scene %s deleted by %s", scene_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scenes/{scene_id}/run", response_model=SceneRunOut)
async def run_scene(scene_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> SceneRunOut:
    """Run a scene now (any member): actions execute in order, failures are reported per action, never raised."""
    scene, _ = await _load_scene(scene_id, user, db)
    results = await SceneRunner(get_runtime()).run_scene(db, scene, source="scene")
    logger.info("Scene %s run by %s: %s", scene.id, user.id, scene_summary(results))
    return SceneRunOut(scene_id=scene.id, name=scene.name, results=results, summary=scene_summary(results), ran_at=scene.last_run_at)


@router.post("/homes/{home_id}/scenes/reorder", response_model=List[SceneOut])
async def reorder_scenes(body: ReorderIn, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> List[SceneOut]:
    """Apply a new order (admin or owner): listed ids first, the others keep their relative order after them."""
    access.require("admin")
    scenes = await _scenes_of(db, access.home.id)
    by_id = {scene.id: scene for scene in scenes}
    unknown = [scene_id for scene_id in body.ids if scene_id not in by_id]
    if unknown:
        raise _bad_request(f"Unknown scene id(s): {', '.join(unknown)}")
    ordered = list(dict.fromkeys(body.ids))
    listed = set(ordered)
    ordered.extend(scene.id for scene in scenes if scene.id not in listed)
    for position, scene_id in enumerate(ordered):
        by_id[scene_id].sort_order = position
    await db.commit()
    return [scene_to_out(scene) for scene in await _scenes_of(db, access.home.id)]


# ----------------------------------------------------------------------------- automations
@router.get("/homes/{home_id}/automations", response_model=List[AutomationOut])
async def list_automations(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> List[AutomationOut]:
    """Automations of a home, oldest first."""
    rows = await db.execute(
        select(Automation).where(Automation.home_id == access.home.id).order_by(Automation.created_at, Automation.name)
    )
    return [automation_to_out(automation) for automation in rows.scalars().all()]


@router.post("/homes/{home_id}/automations", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: AutomationIn, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)
) -> AutomationOut:
    """Create an automation (admin or owner). 400 when a device / scene reference does not belong to the home."""
    access.require("admin")
    await _validate_refs(db, access.home.id, body.actions, body.triggers, body.conditions)
    automation = Automation(
        home_id=access.home.id, name=_clean_name(body.name, "Automation"), enabled=body.enabled, match=body.match,
        triggers=list(body.triggers), conditions=list(body.conditions), actions=list(body.actions),
    )
    db.add(automation)
    await db.commit()
    logger.info("Automation %s (%s) created in home %s by %s", automation.id, automation.name, access.home.id, access.user.id)
    return automation_to_out(automation)


@router.get("/automations/{automation_id}", response_model=AutomationOut)
async def get_automation(
    automation_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AutomationOut:
    """One automation (404 unless the caller is a member of its home)."""
    automation, _ = await _load_automation(automation_id, user, db)
    return automation_to_out(automation)


@router.patch("/automations/{automation_id}", response_model=AutomationOut)
async def update_automation(
    automation_id: str, body: AutomationUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AutomationOut:
    """Update name / enabled / match / triggers / conditions / actions (admin or owner)."""
    automation, access = await _load_automation(automation_id, user, db)
    access.require("admin")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"], "Automation")
    for field in ("triggers", "conditions", "actions"):
        if field in changes and changes[field] is None:
            changes.pop(field)  # explicit null keeps the current list
    if "match" in changes and changes["match"] is None:
        changes.pop("match")
    if any(field in changes for field in ("triggers", "conditions", "actions")):
        await _validate_refs(
            db, automation.home_id,
            changes.get("actions", automation.actions or []),
            changes.get("triggers", automation.triggers or []),
            changes.get("conditions", automation.conditions or []),
        )
    for field, value in changes.items():
        setattr(automation, field, list(value) if isinstance(value, list) else value)
    await db.commit()
    logger.info("Automation %s updated by %s (%s)", automation.id, user.id, ", ".join(sorted(changes)) or "no changes")
    return automation_to_out(automation)


@router.delete("/automations/{automation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_automation(
    automation_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Delete an automation (admin or owner)."""
    automation, access = await _load_automation(automation_id, user, db)
    access.require("admin")
    await db.delete(automation)
    await db.commit()
    logger.info("Automation %s deleted by %s", automation_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _set_enabled(automation_id: str, enabled: bool, user: User, db: AsyncSession) -> AutomationOut:
    automation, access = await _load_automation(automation_id, user, db)
    access.require("admin")
    automation.enabled = enabled
    await db.commit()
    logger.info("Automation %s %s by %s", automation.id, "enabled" if enabled else "disabled", user.id)
    return automation_to_out(automation)


@router.post("/automations/{automation_id}/enable", response_model=AutomationOut)
async def enable_automation(
    automation_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AutomationOut:
    """Enable an automation (admin or owner)."""
    return await _set_enabled(automation_id, True, user, db)


@router.post("/automations/{automation_id}/disable", response_model=AutomationOut)
async def disable_automation(
    automation_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AutomationOut:
    """Disable an automation (admin or owner); the engine ignores it until re-enabled."""
    return await _set_enabled(automation_id, False, user, db)


@router.post("/automations/{automation_id}/trigger", response_model=AutomationTriggerOut)
async def trigger_automation(
    automation_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AutomationTriggerOut:
    """Manual test (any member): run the actions now, ignoring triggers, conditions and the enabled flag."""
    automation, _ = await _load_automation(automation_id, user, db)
    results = await run_automation(get_runtime(), db, automation, source="manual")
    logger.info("Automation %s triggered manually by %s: %s", automation.id, user.id, scene_summary(results))
    return AutomationTriggerOut(
        automation_id=automation.id, name=automation.name, results=results, summary=scene_summary(results),
        triggered_at=automation.last_triggered_at,
    )
