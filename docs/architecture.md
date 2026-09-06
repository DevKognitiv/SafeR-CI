# SafeR CI — System Architecture

## Overview

SafeR CI is a 4-layer open-source safety platform:

```mermaid
graph TB
    subgraph L4["Layer 4 — Mobile App (Flutter)"]
        MA[SafeR Mobile App]
        SOS[SOS Button]
        MAP[Incident Map]
        ALERT[Alert Feed]
    end

    subgraph L3["Layer 3 — Backend (FastAPI)"]
        API[SafeR API Server]
        DB[(PostgreSQL + PostGIS)]
        CACHE[(Redis)]
        WORKER[Celery Workers]
    end

    subgraph L2["Layer 2 — HA Nodes (per neighborhood)"]
        HA1[HA Hub - Yopougon]
        HA2[HA Hub - Cocody]
        HA3[HA Hub - Marcory]
        MQTT[Mosquitto MQTT Broker]
    end

    subgraph L1["Layer 1 — Physical Devices"]
        PB[Panic Buttons]
        SD[Smoke Detectors]
        FD[Flood Sensors]
        GPS[GPS Trackers]
        CAM[IP Cameras]
        LORA[LoRa Nodes]
    end

    subgraph NOTIFY["Notification Channels"]
        FCM[Firebase Push]
        SMS[Twilio SMS]
        WA[WhatsApp Business]
    end

    MA --> API
    SOS --> API
    MAP --> API
    API --> DB
    API --> CACHE
    API --> WORKER
    WORKER --> FCM
    WORKER --> SMS
    WORKER --> WA
    API --> HA1
    API --> HA2
    API --> HA3
    HA1 --> MQTT
    HA2 --> MQTT
    HA3 --> MQTT
    MQTT --> PB
    MQTT --> SD
    MQTT --> FD
    GPS --> HA1
    CAM --> HA1
    LORA --> MQTT
```

---

## Component Details

### Home Assistant Nodes (Layer 2)

Each HA node is deployed as a **neighborhood safety hub** running on a Raspberry Pi 4:

| Component | Specification |
|-----------|--------------|
| Hardware | Raspberry Pi 4 (4GB RAM) |
| OS | Home Assistant OS (HAOS) |
| Power | Solar + LiFePO4 battery backup |
| Connectivity | 4G SIM (primary) + WiFi (secondary) |
| Protocols | Zigbee (XBT-2 dongle), MQTT, REST |
| Local DB | MariaDB (30-day incident history) |

**HA Add-ons installed:**
- Mosquitto MQTT Broker
- Node-RED (visual automation editor)
- MariaDB
- File Editor
- Terminal & SSH

### SafeR API Server (Layer 3)

**Technology:** FastAPI + Python 3.12 + PostgreSQL/PostGIS + Redis

**Key Endpoints:**
```
POST   /api/v1/incidents/          Create new incident
GET    /api/v1/incidents/          List incidents (geo-filtered)
GET    /api/v1/incidents/{id}      Get single incident
PATCH  /api/v1/incidents/{id}      Update status (responders)
POST   /api/v1/incidents/webhook/ha HA node webhook receiver
POST   /api/v1/alerts/broadcast    Send area-wide alert
GET    /api/v1/alerts/active       Get active alerts for location
POST   /api/v1/users/register      Register new user
POST   /api/v1/users/login         Authenticate user
```

### SafeR Hub (Layer 3, `backend/app/hub`)

Multi-brand smart home & security hub mounted at `/api/v1/hub` (also runs standalone on a
Raspberry Pi with SQLite). Brand adapters (Tuya cloud/local, Hikvision ISAPI + AX PRO, Dahua CGI,
Ajax Enterprise API + SIA DC-09 receiver, Matter via python-matter-server, ONVIF, Home Assistant)
normalise devices into one model; homes/rooms/members, scenes, automations, a software alarm
panel, a message centre and a realtime WebSocket sit on top. See [safer-app.md](safer-app.md).

### SafeR App (Layer 4, `mobile/`)

**Technology:** Flutter 3.x + Riverpod + go_router — Tuya-Smart-style UI, French-first.

**Tabs & screens:**
- **Home** — weather header, room tabs, device grid with quick toggles, add device (brand catalogue, category grid, QR scan for Matter/Tuya, dynamic pairing wizards)
- **Device panels** — switch, light (brightness/colour), cover, thermostat, sensors, camera (live stream + PTZ + snapshot), lock, alarm panel (zones), gateway, generic
- **Scenes** — tap-to-run scenes and automations (device/schedule/security triggers, conditions, actions)
- **Security** — arm modes (disarmed/home/away/night), alarm banner, panels/zones/sensors, alarm history, **SOS screen** with local emergency numbers (170, 180, 185, 111)
- **Me** — profile, home management, members, message centre, integrations, settings (language, theme, hub URL), about

---

## Connectivity Fallback Strategy

```
Internet Available → REST API (HTTPS)
        ↓ fails
4G Available → MQTT over cellular
        ↓ fails  
2G Available → SMS via Twilio
        ↓ fails
Local Only → HA automation runs offline (siren, local log)
             Syncs to API when connectivity restored
```

---

## Security Architecture

- **JWT authentication** for all API endpoints
- **Hub webhook secret** — each HA node has a unique signed secret
- **HTTPS everywhere** — Nginx TLS termination
- **Rate limiting** — Redis-based, prevents alert flooding
- **Data locality** — All data stored in-country (VPS in West Africa region)
- **No PII in HA nodes** — Only sensor states, no personal data at the edge

---

## Deployment Topology

```
Internet
    │
    ▼
[Nginx Reverse Proxy + TLS]
    │
    ├── /api/v1/* → [FastAPI Container]
    │                      │
    │               [PostgreSQL + PostGIS]
    │               [Redis Cache]
    │               [Celery Workers]
    │
    └── HA nodes connect via MQTT WebSocket
             │
        [Mosquitto MQTT]
             │
        [HA Hub nodes] → Physical sensors
```

---

## Ivorian Context Adaptations

**Geographic coverage priorities:**
1. Grand Abidjan (Cocody, Yopougon, Marcory, Koumassi, Abobo) — highest density
2. Bouaké — second largest city
3. San Pedro — port city
4. Yamoussoukro — administrative capital
5. Rural communes via LoRaWAN

**Local emergency numbers integrated:**
- 170 — Police Nationale
- 180 — Sapeurs-Pompiers  
- 185 — SAMU
- 111 — Gendarmerie

**Language support:**
- French (primary UI language)
- Dioula (planned v1.1)
- SMS in French (Twilio template)
