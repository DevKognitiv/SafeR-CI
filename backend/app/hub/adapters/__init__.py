"""Import every adapter module so each registers itself on the registry."""
from app.hub.adapters import (  # noqa: F401  pylint: disable=unused-import
    ajax,
    dahua,
    demo,
    hikvision,
    home_assistant,
    matter,
    onvif,
    tuya,
)
from app.hub.adapters.registry import registry  # noqa: F401

__all__ = ["registry"]
