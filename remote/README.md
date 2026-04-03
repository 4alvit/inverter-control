# Remote Web Dashboard

Standalone web server that connects to Cerbo GX via MQTT.

This separates the lightweight control loop (runs 24/7 on Cerbo GX) from the heavy web interface (runs on any Linux server with pip3/FastAPI).

## Architecture

```
┌─────────────────────┐     MQTT      ┌─────────────────────┐
│     Cerbo GX        │──────────────▶│   Linux Server      │
│                     │               │                     │
│  inverter-control   │               │  remote/server.py   │
│  (main.py)          │◀──────────────│  FastAPI + Vue.js   │
│                     │   Commands    │  WebSocket + uPlot  │
│  MQTT Publisher     │               │  MQTT Subscriber    │
└─────────────────────┘               └─────────────────────┘
        │                                      │
        │ D-Bus                                │ HTTPS
        ▼                                      ▼
   [Victron]                              [Browser]
```

## Prerequisites

1. MQTT Broker running (e.g., Mosquitto on your Linux server or existing broker)
2. Cerbo GX with inverter-control configured to publish to MQTT

## Quick Start

### 1. Configure MQTT on Cerbo

Edit `/data/apps/inverter_control/config.py`:
```python
MQTT_BROKER = "192.168.x.x"  # Your MQTT broker IP
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "inverter"
```

### 2. Start Remote Dashboard

```bash
# On Linux server
cd remote
pip3 install -r requirements.txt
python3 server.py --mqtt-host <BROKER_IP>

# With SSL
python3 server.py --mqtt-host <BROKER_IP> --ssl-cert cert.pem --ssl-key key.pem
```

## Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| MQTT_HOST | 192.168.160.150 | Cerbo GX IP |
| MQTT_PORT | 1883 | MQTT port |
| WEB_PORT | 8080 | Web server port |
| SSL_CERT | None | SSL certificate path |
| SSL_KEY | None | SSL key path |

## MQTT Topics

### Published by Cerbo (inverter-control)
- `inverter/state` - Full state JSON (every 0.5s)
- `inverter/console` - Console output lines

### Subscribed by Cerbo (commands)
- `inverter/cmd/setpoint` - Set manual setpoint
- `inverter/cmd/toggle` - Toggle HA entity
- `inverter/cmd/dry_run` - Toggle dry run
- `inverter/cmd/limits` - Set power limits
- `inverter/cmd/ess_mode` - Toggle ESS mode
