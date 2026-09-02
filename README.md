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

## 🏗️ Architecture (4 Layers)

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4 — Mobile App (Flutter, French-first)                   │
│  SOS Button · Incident Map · Push Alerts · Responder Mode       │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS / WebSocket
┌────────────────────────▼────────────────────────────────────────┐
│  Layer 3 — SafeR API Server (FastAPI + PostgreSQL + Redis)      │
│  User Auth · Incident Mgmt · Geo Alerts · Analytics Dashboard   │
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

> **Component maturity varies a lot.** See [`docs/STATUS.md`](docs/STATUS.md) for the
> authoritative breakdown of what runs today and what is still a scaffold.

```
SafeR-CI/
├── web-dashboard/               # ✅ Next.js 14 incident dashboard — runs today
│   └── src/
│       ├── app/                 #    App Router pages + demo API routes
│       ├── components/          #    SOSButton, IncidentMap, AlertFeed, StatCard
│       ├── lib/                 #    Demo incident data + helpers
│       └── types/               #    Shared Incident type
├── ha-config/                   # ✅ Home Assistant config — complete, untested on hardware
│   ├── automations/             #    Panic, fire, flood, bidirectional mobile control
│   ├── dashboards/              #    6-view Lovelace UI
│   ├── entities/                #    Entity definitions
│   ├── scripts/                 #    Emergency scripts
│   ├── configuration.yaml
│   ├── rest_commands.yaml
│   └── secrets.yaml.example
├── backend/                     # 🚧 FastAPI server — scaffold, does not import yet
│   └── app/
│       ├── api/routes/          #    incidents.py only
│       ├── core/                #    config.py only
│       └── models/              #    incident.py only
├── mobile/                      # 🚧 Flutter app — scaffold, does not build yet
│   └── lib/                     #    main.dart, sos_screen.dart, sos_button.dart
└── docs/                        # Architecture, deployment, status, contributing
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
| Mobile | **Flutter 3.x** | iOS + Android, French-first |
| Maps | OpenStreetMap + flutter_map | Zero-cost mapping |
| Push | Firebase Cloud Messaging | Mobile push alerts |
| Messaging | WhatsApp Business API | High-penetration CI fallback |
| Dashboard | **Next.js 14 + TypeScript** | Web incident dashboard |
| Deploy | Docker Compose + Nginx | Self-hosted or cloud VPS |

---

## 🚀 Milestones

### 🔄 v0.1 — MVP: Panic Button Alert
- [x] Repository scaffolded
- [x] HA configuration & automations (panic, fire, flood)
- [x] Web dashboard with live incident map + SOS (demo data)
- [ ] FastAPI backend — model & routes drafted, service/schema layer missing
- [ ] Flutter SOS screen — drafted, app does not build yet
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

The web dashboard is the fastest way to see SafeR CI running:

```bash
git clone https://github.com/DevKognitiv/SafeR-CI.git
cd SafeR-CI/web-dashboard
npm install
npm run dev          # http://localhost:3000
```

It runs on demo data with an in-memory API — no database or backend required.

For a Home Assistant hub, copy `ha-config/` to your HA `/config/` directory and build
`secrets.yaml` from `secrets.yaml.example`. See [docs/deployment.md](docs/deployment.md).

The FastAPI backend and Flutter app are **not yet runnable** — see [docs/STATUS.md](docs/STATUS.md).

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

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md), and [docs/STATUS.md](docs/STATUS.md) for where
help is most needed. PRs welcome on all layers!

## 📄 License

Apache 2.0 — [LICENSE](LICENSE)

*SafeR CI — Bâti avec ❤️ pour les communautés de Côte d'Ivoire.*
