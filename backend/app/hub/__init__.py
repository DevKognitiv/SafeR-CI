"""
SafeR Hub — multi-brand smart home & security hub.

Normalises Tuya, Hikvision, Dahua, Ajax, Matter, ONVIF and Home Assistant devices
into one device model and exposes the Hub API used by the SafeR mobile app.

The package is self-contained: it does not import the (incomplete) legacy backend
modules and can run standalone via ``uvicorn app.hub.app:app``.
"""

__version__ = "0.2.0"
