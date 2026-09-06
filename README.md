# 🛡️ SafeR-CI

**Open-source safety & emergency response platform for Côte d'Ivoire**

Built on [Home Assistant](https://www.home-assistant.io/), MQTT, FastAPI, and Flutter — designed for resilient, local-first community safety across Côte d'Ivoire.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.4-blue)](https://www.home-assistant.io/)
[![Flutter](https://img.shields.io/badge/Flutter-3.x-blue)](https://flutter.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)](https://fastapi.tiangolo.com/)

---

## 🌍 Vision

SafeR CI is a community safety platform built for the realities of Côte d'Ivoire: unreliable connectivity, mixed urban/rural geography, high mobile penetration, and limited emergency infrastructure. It connects physical sensors (panic buttons, smoke detectors, flood sensors) with a mobile app, SMS fallback, and a national incident dashboard — all powered by open-source technology with zero licensing cost.

---

## 📱 SafeR app — smart home & security (new)

The mobile app is now a **Tuya-Smart-style smart home & security app named SafeR**: one app to
onboard and control devices from **Tuya, Hikvision, Dahua, Ajax, Matter, ONVIF cameras and Home
Assistant**, with rooms, tap-to-run scenes, automations, a Security tab (arm modes, alarm banner,
zones) and the SafeR CI SOS button. It is backed by the **SafeR Hub** (`backend/app/hub`), a
multi-brand hub API with a unified device model, realtime WebSocket updates, a software alarm
panel, a SIA DC-09 receiver and a Matter controller bridge.

➡️ [docs/safer-app.md](docs/safer-app.md) · [docs/device-onboarding.md](docs/device-onboarding.md)

---

## 🏗️ Architecture (4 Layers)

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4 — SafeR App (Flutter, French-first, Tuya-style)        │
│  Devices · Scenes · Security · SOS · Multi-brand onboarding     │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS / WebSocket
┌────────────────────────▼────────────────────────────────────────┐
│  Layer 3 — SafeR API + SafeR Hub (FastAPI + PostgreSQL + Redis) │
│  Incidents · Geo Alerts · Hub: Tuya/Hik/Dahua/Ajax/Matter/HA    │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST / MQTT / Webhooks
┌────────────────────────▼────────────────────────────────────────┐
│  Layer 2 — Home Assistant Nodes (local safety hubs)             │
│  Per-neighborhood Raspberry Pi · Automations · Sensor Bridge    │
└────────────────────────┬────────────────────────────────────────┘
                         │ Zigbee · Z-Wave · LoRaWAN · MQTT
┌────────────────────────▼────────────────────────────────────────┐
│  Layer 1 — Physical Devices                                     │
│  Panic Buttons · Smoke/Fire · Flood Sensors · GPS · Cameras     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Repository Structure

```
SafeR-CI/
├── ha-config/                   # Home Assistant configuration & automations
│   ├── automations/             # YAML automations (panic, fire, flood)
│   ├── custom_components/       # Custom HA integrations
│   ├── dashboards/              # Lovelace UI dashboards
│   └── configuration.yaml
├── backend/                     # FastAPI server (Python 3.11+)
│   ├── app/
│   │   ├── api/routes/          # Incident REST endpoints
│   │   ├── hub/                 # SafeR Hub: multi-brand smart home & security API
│   │   │   ├── adapters/        # tuya, hikvision, dahua, ajax, matter, onvif, home_assistant, demo
│   │   │   ├── routes/          # auth, homes, devices, onboarding, scenes, security, messages, ws
│   │   │   ├── services/        # device service, poller, subscriptions, SIA DC-09 receiver, SOS
│   │   │   ├── automation/      # scene runner + automation engine
│   │   │   └── tests/           # pytest suite (no network)
│   │   ├── models/              # SQLAlchemy + PostGIS models
│   │   └── main.py
│   ├── requirements.txt
│   └── docker-compose.yml       # api, db, redis, celery, matter-server, nginx
├── mobile/                      # SafeR Flutter app (Android, iOS, web)
│   ├── lib/
│   │   ├── core/                # api client, websocket, models, providers, router, theme, i18n
│   │   └── features/            # auth, home, add_device, device panels, scenes, security, me
│   ├── test/                    # widget + unit tests
│   └── pubspec.yaml
├── infrastructure/              # Docker, Nginx, Terraform
└── docs/                        # Architecture, API, deployment guides
```

---

## 🔧 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| IoT Hub | **Home Assistant 2026.x** | Local sensor management, automations |
| Protocol | MQTT (Mosquitto) | Low-bandwidth device communication |
| Rural | LoRaWAN (The Things Network) | Off-grid sensor coverage |
| SMS | Twilio | Alerts for non-smartphone users |
| Backend | **FastAPI + Python 3.12** | Central API server |
| Database | PostgreSQL + PostGIS | Geo-aware incident storage |
| Cache | Redis + Celery | Real-time alerts, async tasks |
| Mobile | **Flutter 3.x** + Riverpod + go_router | SafeR app: iOS + Android + web, French-first |
| Smart home | **SafeR Hub** (FastAPI) | Tuya Cloud/local, Hikvision ISAPI, Dahua CGI, Ajax API + SIA DC-09, Matter (python-matter-server), ONVIF, Home Assistant |
| Maps | OpenStreetMap + flutter_map | Zero-cost mapping |
| Push | Firebase Cloud Messaging | Mobile push alerts |
| Messaging | WhatsApp Business API | High-penetration CI fallback |
| Deploy | Docker Compose + Nginx | Self-hosted or cloud VPS |

---

## 🚀 Milestones

### ✅ v0.1 — MVP: Panic Button Alert
- [x] Repository scaffolded
- [x] HA configuration & automations (panic, fire, flood)
- [x] FastAPI backend with incident model & routes
- [x] Flutter SOS screen with one-tap alert
- [ ] End-to-end test on hardware

### 🔲 v0.2 — Community Safety Map
- [ ] Flutter: Live incident map (OpenStreetMap)
- [ ] FastAPI: GET /incidents with PostGIS geo filtering
- [ ] Firebase push notification integration
- [ ] Community incident reporting with photo

### 🔲 v1.0 — Full Platform
- [ ] Multi-node HA aggregation
- [ ] Responder dashboard
- [ ] LoRaWAN sensor support
- [ ] Analytics by commune/region
- [ ] WhatsApp bot for feature-phone users
- [ ] Offline-first mobile with sync queue

---

## 🛠️ Quick Start

```bash
git clone https://github.com/DevKognitiv/SafeR-CI.git
cd SafeR-CI

# Start backend
cd backend && cp .env.example .env && docker-compose up -d

# Run the SafeR Hub alone (SQLite, no Docker)
cd backend && pip install -r requirements.txt aiosqlite && SECRET_KEY=dev uvicorn app.hub.app:app --port 8000

# Run the SafeR app
cd ../mobile && flutter pub get && flutter run --dart-define=SAFER_HUB_URL=http://10.0.2.2:8000
```

See [docs/deployment.md](docs/deployment.md) for the full guide.

---

## 🌐 Connectivity for Côte d'Ivoire

| Scenario | Transport | Mechanism |
|----------|-----------|-----------|
| Urban Abidjan | 4G / WiFi | Full REST API |
| Peri-urban | 3G / 2G | Compressed payloads |
| SMS fallback | GSM | Twilio → incident creation |
| Rural off-grid | LoRaWAN | TTN → MQTT → HA |
| Offline | No internet | HA runs autonomously, syncs later |

---

## 📞 Emergency Numbers (CI)

| Service | Number |
|---------|--------|
| Police Nationale | **170** |
| Sapeurs-Pompiers | **180** |
| SAMU | **185** |
| Gendarmerie | **111** |

---

## 🤝 Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md). PRs welcome on all layers!

## 📄 License

Apache 2.0 — [LICENSE](LICENSE)

*SafeR CI — Bâti avec ❤️ pour les communautés de Côte d'Ivoire.*
