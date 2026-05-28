"""
SafeR CI — Notification service
Fan-out of incident alerts to downstream channels (push / SMS / MQTT).

This is intentionally a thin, dependency-free implementation: the real
integrations (Firebase, Twilio, MQTT) are configured via settings and can
be wired in here without changing the call sites.
"""
import logging

logger = logging.getLogger("safer.notifications")


class NotificationService:
    async def broadcast_incident_alert(self, *, incident) -> None:
        """Notify responders/citizens about a new or updated incident.

        Runs as a FastAPI background task, so failures here must never
        bubble up into the request/response cycle.
        """
        try:
            logger.info(
                "incident_alert id=%s type=%s severity=%s commune=%s",
                getattr(incident, "id", "?"),
                getattr(incident, "incident_type", "?"),
                getattr(incident, "severity", "?"),
                getattr(incident, "commune", "?"),
            )
            # TODO: push (Firebase), SMS (Twilio), MQTT fan-out.
        except Exception:  # pragma: no cover - defensive, background task
            logger.exception("failed to broadcast incident alert")
