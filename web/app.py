#!/usr/bin/env python3
"""
FastAPI Web Server for Inverter Control
Real-time dashboard with WebSocket and MsgPack
"""

import asyncio
import time
import logging
import msgpack
from collections import deque
from typing import Dict, Any, Callable, List, Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

logger = logging.getLogger('inverter-control')

# Callbacks set by main.py
state_getter: Callable[[], Dict[str, Any]] = lambda: {}
setpoint_setter: Callable[[int], bool] = lambda x: False
dry_run_toggler: Callable[[], bool] = lambda: False
limits_setter: Callable[[int, int], Dict[str, int]] = lambda mn, mx: {'min': mn, 'max': mx}
ess_mode_toggler: Callable[[], Dict[str, Any]] = lambda: {}
loop_interval_setter: Callable[[float], float] = lambda x: x
ha_client = None

# History for graphs
history = {
    'timestamps': deque(maxlen=1800),
    'grid': deque(maxlen=1800),
    'solar': deque(maxlen=1800),
    'battery': deque(maxlen=1800),
    'setpoint': deque(maxlen=1800),
    'consumption': deque(maxlen=1800),
}

console_log = deque(maxlen=50)

# WebSocket clients
ws_clients: Set[WebSocket] = set()
ws_lock = asyncio.Lock()


def add_history_point(data: Dict[str, Any]):
    """Add a data point to history"""
    history['timestamps'].append(time.time())
    history['grid'].append(data.get('gt', 0))
    history['solar'].append(data.get('solar_total', 0))
    history['battery'].append(data.get('battery_power', 0))
    history['setpoint'].append(data.get('setpoint', 0))
    history['consumption'].append(data.get('tt', 0))


def add_console_line(line: str):
    """Add line to console log"""
    console_log.append(line)


async def broadcast_state():
    """Broadcast state to all WebSocket clients using MsgPack"""
    if not ws_clients:
        return
    
    state = state_getter()
    state['console'] = list(console_log)
    state['history'] = {
        'timestamps': list(history['timestamps']),
        'grid': list(history['grid']),
        'solar': list(history['solar']),
        'battery': list(history['battery']),
        'setpoint': list(history['setpoint']),
        'consumption': list(history['consumption']),
    }
    
    data = msgpack.packb(state, use_bin_type=True)
    
    async with ws_lock:
        dead = []
        for ws in ws_clients:
            try:
                await ws.send_bytes(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Start background broadcaster
    async def broadcaster():
        while True:
            await broadcast_state()
            await asyncio.sleep(0.5)
    
    task = asyncio.create_task(broadcaster())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    async with ws_lock:
        ws_clients.add(websocket)
    
    try:
        while True:
            data = await websocket.receive_bytes()
            msg = msgpack.unpackb(data, raw=False)
            action = msg.get('action')
            
            if action == 'toggle':
                entity = msg.get('entity')
                if entity and ha_client:
                    ha_client.toggle_entity(entity)
            
            elif action == 'press':
                entity = msg.get('entity')
                if entity and ha_client:
                    ha_client.press_button(entity)
            
            elif action == 'setpoint':
                value = msg.get('value')
                if value is not None:
                    setpoint_setter(int(value))
            
            elif action == 'dry_run':
                dry_run_toggler()
            
            elif action == 'limits':
                limits_setter(msg.get('min', -2300), msg.get('max', 2250))
            
            elif action == 'ess_mode':
                ess_mode_toggler()
            
            elif action == 'loop_interval':
                loop_interval_setter(msg.get('interval', 0.33))
    
    except WebSocketDisconnect:
        pass
    finally:
        async with ws_lock:
            ws_clients.discard(websocket)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve Vue.js dashboard"""
    return get_dashboard_html()


@app.get("/api/state")
async def api_state():
    """Fallback REST endpoint"""
    return state_getter()


def get_dashboard_html() -> str:
    """Generate Vue.js + uPlot dashboard HTML"""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Inverter Control</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/vue@3.4.21/dist/vue.global.prod.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/uplot@1.6.30/dist/uPlot.iife.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uplot@1.6.30/dist/uPlot.min.css">
    <script src="https://cdn.jsdelivr.net/npm/msgpack-lite@0.1.26/dist/msgpack.min.js"></script>
    <style>
        :root {
            --bg-dark: #0a0a0a;
            --bg-card: #151515;
            --border: #2a2a2a;
            --text: #e0e0e0;
            --text-dim: #666;
            --accent: #00d4aa;
            --solar: #f5a623;
            --grid: #4a90d9;
            --battery: #7ed321;
            --consumption: #e74c3c;
        }
        body { 
            background: var(--bg-dark); 
            color: var(--text); 
            font-family: 'Segoe UI', system-ui, sans-serif;
            min-height: 100vh;
        }
        .card { 
            background: var(--bg-card); 
            border: 1px solid var(--border); 
            border-radius: 8px;
        }
        .card-header {
            background: transparent;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 1px;
            color: var(--text-dim);
            padding: 6px 12px;
        }
        .card-body { padding: 8px 12px; }
        .stat-value { font-size: 1.6rem; font-weight: 700; line-height: 1; }
        .stat-label { font-size: 0.65rem; color: var(--text-dim); text-transform: uppercase; }
        .stat-sub { font-size: 0.75rem; color: var(--text-dim); margin-top: 2px; }
        .toggle-btn {
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.45rem;
            font-weight: 600;
            border: 1px solid var(--border);
            transition: all 0.15s;
            display: inline-block;
            margin: 1px;
        }
        .toggle-btn.on { background: #2e7d32; border-color: #4caf50; color: #fff; }
        .toggle-btn.off { background: #1a1a1a; color: #555; }
        .toggle-btn.pending { background: #000; color: #333; border-color: #333; }
        .toggle-btn:hover { transform: scale(1.02); filter: brightness(1.1); }
        #console {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.45rem;
            background: #000;
            color: #0f0;
            padding: 6px;
            height: 180px;
            overflow-y: auto;
            border-radius: 6px;
        }
        .text-solar { color: var(--solar); }
        .text-grid { color: var(--grid); }
        .text-battery { color: var(--battery); }
        .text-consumption { color: var(--consumption); }
        .text-accent { color: var(--accent); }
        .daily-stats {
            font-size: 0.75rem;
            color: var(--text-dim);
            padding: 8px 12px;
            background: #0d0d0d;
            border-radius: 6px;
            font-family: monospace;
        }
        .update-dot { 
            width: 10px; height: 10px; border-radius: 50%; 
            background: #333; display: inline-block; 
            transition: background 0.1s;
        }
        .update-dot.active { background: #f44336; box-shadow: 0 0 8px #f44336; }
        .chart-wrap { height: 200px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
        .status-dot.online { background: #4caf50; }
        .status-dot.offline { background: #f44336; }
        .compact-controls input { font-size: 0.65rem !important; padding: 2px 6px !important; }
        .compact-controls button { font-size: 0.65rem !important; padding: 2px 8px !important; }
        #loads { font-size: 0.65rem; color: #888; }
    </style>
</head>
<body>
<div id="app" class="container-fluid p-2">
    <!-- Header -->
    <div class="card mb-2">
        <div class="card-body py-1 px-2">
            <div class="d-flex flex-wrap gap-1 align-items-center">
                <span class="update-dot" :class="{active: pulse}"></span>
                <div class="toggle-btn" :class="state.dry_run ? 'on' : 'off'" @click="send('dry_run')">
                    <i class="fas fa-flask me-1"></i>DRY
                </div>
                <div class="toggle-btn" :class="essClass" @click="send('ess_mode')">
                    <i class="fas fa-bolt me-1"></i>{{ essText }}
                </div>
                <div class="vr mx-1" style="border-left:1px solid #333;height:16px;"></div>
                <div v-for="(val, key) in state.booleans" :key="key" 
                     class="toggle-btn" :class="val ? 'on' : 'off'"
                     @click="send('toggle', {entity: 'input_boolean.' + key})">
                    {{ formatKey(key) }}
                </div>
            </div>
        </div>
    </div>
    
    <!-- Daily stats -->
    <div class="daily-stats mb-2" v-html="dailyStatsHtml"></div>
    
    <!-- Main stats -->
    <div class="row g-2 mb-2">
        <div class="col-md-2">
            <div class="card h-100"><div class="card-body text-center">
                <div class="stat-label">Grid</div>
                <div class="stat-value text-grid">{{ formatPower(state.gt) }}</div>
                <div class="stat-sub">{{ formatPower(state.g1) }} | {{ formatPower(state.g2) }}</div>
            </div></div>
        </div>
        <div class="col-md-2">
            <div class="card h-100"><div class="card-body text-center">
                <div class="stat-label">Consumption</div>
                <div class="stat-value text-consumption">{{ formatPower(state.tt) }}</div>
                <div class="stat-sub">{{ formatPower(state.t1) }} | {{ formatPower(state.t2) }}</div>
            </div></div>
        </div>
        <div class="col-md-3">
            <div class="card h-100"><div class="card-body text-center">
                <div class="stat-label">Solar</div>
                <div class="stat-value text-solar">{{ formatPower(state.solar_total) }}</div>
                <div class="stat-sub">{{ solarDetail }}</div>
            </div></div>
        </div>
        <div class="col-md-3">
            <div class="card h-100"><div class="card-body text-center">
                <div class="stat-label">Battery</div>
                <div class="stat-value text-battery">{{ Math.floor(state.battery_soc || 0) }}%</div>
                <div class="stat-sub">{{ formatPower(state.battery_power) }} | {{ (state.battery_voltage || 0).toFixed(2) }}V</div>
            </div></div>
        </div>
        <div class="col-md-2">
            <div class="card h-100"><div class="card-body text-center">
                <div class="stat-label">Setpoint</div>
                <div class="stat-value text-accent">{{ formatPower(state.setpoint) }}</div>
                <div class="stat-sub">{{ state.inverter_state || '--' }}</div>
            </div></div>
        </div>
    </div>
    
    <!-- Chart -->
    <div class="row g-2 mb-2">
        <div class="col-md-8">
            <div class="card"><div class="card-body py-1">
                <div class="chart-wrap" ref="chartEl"></div>
            </div></div>
        </div>
        <div class="col-md-4">
            <!-- EV -->
            <div class="card mb-2" v-if="state.features?.ev !== false">
                <div class="card-header"><i class="fas fa-car me-2"></i>EV</div>
                <div class="card-body py-1">
                    <div class="d-flex justify-content-between">
                        <div><div class="stat-value text-solar">{{ evCharging }}</div><div class="stat-sub">Charging</div></div>
                        <div class="text-center"><div class="stat-value" style="color:#9e9e9e">{{ evPower }}</div><div class="stat-sub">VUE</div></div>
                        <div class="text-end"><div class="stat-value text-accent">{{ Math.floor(state.car_soc || 0) }}%</div><div class="stat-sub">SoC</div></div>
                    </div>
                </div>
            </div>
            <!-- Water -->
            <div class="card mb-2" v-if="state.features?.water !== false">
                <div class="card-header"><i class="fas fa-faucet me-2"></i>Water</div>
                <div class="card-body py-1">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="fw-bold" :style="{color: state.water_valve ? '#f44336' : '#4caf50'}">{{ state.water_level || 0 }} cm</div>
                        <div class="d-flex gap-1">
                            <div class="toggle-btn" :class="state.pump_switch ? 'on' : 'off'" @click="send('toggle', {entity:'switch.pump_switch'})">PUMP</div>
                            <div class="toggle-btn" :class="state.water_valve ? 'on' : 'off'" @click="send('toggle', {entity:'switch.778_40th_ave_sf_shutoff_valve'})">VALVE</div>
                        </div>
                    </div>
                </div>
            </div>
            <!-- Home -->
            <div class="card" v-if="state.features?.ha !== false">
                <div class="card-header"><i class="fas fa-home me-2"></i>Home</div>
                <div class="card-body py-1">
                    <div class="d-flex gap-1 flex-wrap">
                        <div class="toggle-btn" :class="state.home_recliner ? 'on' : 'off'" @click="send('toggle', {entity:'switch.recliner_recliner'})">RECLINER</div>
                        <div class="toggle-btn" :class="state.home_garage ? 'on' : 'off'" @click="send('toggle', {entity:'switch.garage_opener_l'})">GARAGE</div>
                        <div class="toggle-btn" :class="state.laundry_outlet ? 'on' : 'off'" @click="send('toggle', {entity:'switch.laundry_zigbee_switch'})">LAUNDRY</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Console & Loads -->
    <div class="row g-2 mb-2">
        <div class="col-md-8">
            <div class="card"><div class="card-body p-1">
                <div id="console" ref="consoleEl">
                    <div v-for="(line, i) in state.console" :key="i">{{ line }}</div>
                </div>
            </div></div>
        </div>
        <div class="col-md-4" v-if="state.features?.ha_loads !== false">
            <div class="card">
                <div class="card-header">Loads</div>
                <div class="card-body py-1">
                    <div id="loads">
                        <div v-for="[name, val] in sortedLoads" :key="name" class="d-flex justify-content-between">
                            <span>{{ name }}</span><span>{{ Math.floor(val) }}W</span>
                        </div>
                        <div v-if="!sortedLoads.length" class="text-muted">No active loads</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Controls -->
    <div class="row g-2 compact-controls">
        <div class="col-md-4">
            <div class="card"><div class="card-body">
                <div class="d-flex gap-1 align-items-center">
                    <input type="number" v-model.number="manualSetpoint" class="form-control form-control-sm" placeholder="W" style="width:70px;background:#1a1a1a;border-color:#333;color:#ddd;">
                    <button class="btn btn-sm btn-success" @click="sendSetpoint">Set</button>
                    <small class="ms-1" style="color:#999">[{{ state.limits?.min }}, +{{ state.limits?.max }}]</small>
                </div>
            </div></div>
        </div>
        <div class="col-md-5">
            <div class="card"><div class="card-body">
                <div class="d-flex gap-1 align-items-center flex-wrap">
                    <span class="text-muted">Min:</span>
                    <input type="number" v-model.number="limitMin" class="form-control form-control-sm" style="width:60px;background:#1a1a1a;border-color:#333;color:#ddd;">
                    <span class="text-muted">Max:</span>
                    <input type="number" v-model.number="limitMax" class="form-control form-control-sm" style="width:60px;background:#1a1a1a;border-color:#333;color:#ddd;">
                    <button class="btn btn-sm btn-warning" @click="sendLimits">Apply</button>
                </div>
            </div></div>
        </div>
        <div class="col-md-3">
            <div class="card"><div class="card-body">
                <div class="d-flex gap-1 align-items-center">
                    <input type="number" v-model.number="loopInterval" step="0.1" class="form-control form-control-sm" style="width:60px;background:#1a1a1a;border-color:#333;color:#ddd;">
                    <span class="text-muted">s</span>
                    <button class="btn btn-sm btn-info" @click="sendLoopInterval">Set</button>
                </div>
            </div></div>
        </div>
    </div>
    
    <!-- Status -->
    <div class="mt-2 text-center small" style="color:#888">
        <span class="status-dot" :class="state.ha_connected ? 'online' : 'offline'"></span>
        <span>HA: {{ state.ha_connected ? 'Connected' : 'Disconnected' }}</span>
        &nbsp;|&nbsp; <span>{{ lastUpdateText }}</span>
        &nbsp;|&nbsp; <span>Uptime: {{ formatUptime(state.uptime || 0) }}</span>
        &nbsp;|&nbsp; <span :style="{color: wsConnected ? '#4caf50' : '#f44336'}">WS: {{ wsConnected ? 'OK' : 'Reconnecting...' }}</span>
    </div>
</div>

<script>
const { createApp, ref, computed, onMounted, onUnmounted, watch, nextTick } = Vue;

createApp({
    setup() {
        const state = ref({booleans: {}, features: {}, limits: {min: -2300, max: 2250}, console: []});
        const pulse = ref(false);
        const wsConnected = ref(false);
        const lastUpdate = ref(Date.now());
        const chartEl = ref(null);
        const consoleEl = ref(null);
        let ws = null;
        let chart = null;
        let reconnectTimer = null;
        
        const manualSetpoint = ref(null);
        const limitMin = ref(-2300);
        const limitMax = ref(2250);
        const loopInterval = ref(0.33);
        
        function connect() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${proto}//${location.host}/ws`);
            ws.binaryType = 'arraybuffer';
            
            ws.onopen = () => { wsConnected.value = true; };
            ws.onclose = () => { 
                wsConnected.value = false; 
                reconnectTimer = setTimeout(connect, 2000);
            };
            ws.onmessage = (e) => {
                const data = msgpack.decode(new Uint8Array(e.data));
                state.value = data;
                lastUpdate.value = Date.now();
                pulse.value = !pulse.value;
                
                if (data.limits) {
                    limitMin.value = data.limits.min;
                    limitMax.value = data.limits.max;
                }
                if (data.loop_interval) loopInterval.value = data.loop_interval;
                
                updateChart(data.history);
                nextTick(() => {
                    if (consoleEl.value) consoleEl.value.scrollTop = 99999;
                });
            };
        }
        
        function send(action, payload = {}) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(msgpack.encode({action, ...payload}));
            }
        }
        
        function sendSetpoint() {
            if (manualSetpoint.value !== null) {
                send('setpoint', {value: manualSetpoint.value});
                manualSetpoint.value = null;
            }
        }
        function sendLimits() { send('limits', {min: limitMin.value, max: limitMax.value}); }
        function sendLoopInterval() { send('loop_interval', {interval: loopInterval.value}); }
        
        function formatPower(w) {
            const v = Math.abs(Math.floor(w || 0));
            const sign = w < 0 ? '-' : '';
            return v >= 1000 ? sign + (v/1000).toFixed(1) + 'kW' : sign + v + 'W';
        }
        function formatKey(k) { return k.replace(/_/g, ' ').toUpperCase(); }
        function formatUptime(s) {
            if (s < 60) return s + 's';
            if (s < 3600) return Math.floor(s/60) + 'm';
            const h = Math.floor(s/3600), m = Math.floor((s%3600)/60);
            return h + 'h ' + m + 'm';
        }
        
        const lastUpdateText = computed(() => {
            const s = Math.floor((Date.now() - lastUpdate.value) / 1000);
            return s < 60 ? s + 's ago' : Math.floor(s/60) + 'm ago';
        });
        
        const essClass = computed(() => {
            const m = state.value.ess_mode;
            if (!m) return 'off';
            if (m.mode_name === 'Off' || m.mode_name === 'Charger only') return 'off';
            return 'on';
        });
        const essText = computed(() => {
            const m = state.value.ess_mode;
            if (!m) return 'ESS';
            if (m.is_external) return 'External';
            return m.mode_name || 'ESS';
        });
        
        const solarDetail = computed(() => {
            const mppt = state.value.mppt_individual || [];
            const tas = state.value.tasmota_individual || [];
            const mpptStr = mppt.length ? mppt.map(v => Math.floor(v) + 'W').join('|') : '--';
            const tasStr = tas.length ? tas.map(v => Math.floor(v) + 'W').join('|') : '--';
            return mpptStr + ' | ' + tasStr;
        });
        
        const evCharging = computed(() => {
            const kw = parseFloat(state.value.ev_charging_kw) || 0;
            return kw > 0 ? kw.toFixed(1) + 'kW' : '0';
        });
        const evPower = computed(() => formatPower(state.value.ev_power || 0));
        
        const sortedLoads = computed(() => {
            const loads = state.value.loads || {};
            return Object.entries(loads)
                .filter(([_, v]) => v > 10)
                .sort((a, b) => b[1] - a[1]);
        });
        
        const dailyStatsHtml = computed(() => {
            const ds = state.value.daily_stats || {};
            const prod = (ds.produced_today || 0).toFixed(2);
            const dollars = (ds.produced_dollars || 0).toFixed(2);
            const grid = (ds.grid_kwh || 0).toFixed(2);
            return `<span style="color:#f5a623">☀️ ${prod}kWh</span> <span style="color:#4caf50">($${dollars})</span> | Grid: ${grid}kWh`;
        });
        
        function initChart() {
            const opts = {
                width: chartEl.value.clientWidth,
                height: 200,
                series: [
                    {},
                    {stroke: '#4a90d9', fill: 'rgba(74,144,217,0.05)', label: 'Grid'},
                    {stroke: '#f5a623', fill: 'rgba(245,166,35,0.05)', label: 'Solar'},
                    {stroke: '#7ed321', fill: 'rgba(126,211,33,0.05)', label: 'Battery'},
                    {stroke: '#00d4aa', dash: [5,5], label: 'Setpoint'},
                ],
                axes: [
                    {show: false},
                    {grid: {stroke: '#222'}, ticks: {stroke: '#222'}, values: (u, v) => v.map(n => n + 'W')}
                ],
                legend: {show: true},
                cursor: {show: false},
            };
            chart = new uPlot(opts, [[], [], [], [], []], chartEl.value);
        }
        
        function updateChart(hist) {
            if (!chart || !hist || !hist.timestamps?.length) return;
            chart.setData([
                hist.timestamps,
                hist.grid,
                hist.solar,
                hist.battery,
                hist.setpoint
            ]);
        }
        
        onMounted(() => {
            connect();
            nextTick(() => initChart());
            
            window.addEventListener('resize', () => {
                if (chart && chartEl.value) chart.setSize({width: chartEl.value.clientWidth, height: 200});
            });
            
            setInterval(() => { lastUpdate.value = lastUpdate.value; }, 1000);
        });
        
        onUnmounted(() => {
            if (ws) ws.close();
            if (reconnectTimer) clearTimeout(reconnectTimer);
        });
        
        return {
            state, pulse, wsConnected, lastUpdateText, chartEl, consoleEl,
            manualSetpoint, limitMin, limitMax, loopInterval,
            essClass, essText, solarDetail, evCharging, evPower, sortedLoads, dailyStatsHtml,
            send, sendSetpoint, sendLimits, sendLoopInterval,
            formatPower, formatKey, formatUptime
        };
    }
}).mount('#app');
</script>
</body>
</html>'''


# TCP console streaming (keep for backward compat)
import socket
import select

TCP_CONSOLE_PORT = 9999
_tcp_clients = []
_tcp_clients_lock = asyncio.Lock()
_tcp_server = None


async def _tcp_accept_loop(server):
    """Accept TCP connections for console streaming"""
    while True:
        try:
            client, addr = await asyncio.get_event_loop().run_in_executor(None, server.accept)
            client.setblocking(False)
            async with _tcp_clients_lock:
                _tcp_clients.append(client)
            logger.info(f"TCP console client connected: {addr}")
        except Exception:
            break


def broadcast_console_tcp(line: str):
    """Broadcast line to TCP clients"""
    if not _tcp_clients:
        return
    data = (line + '\n').encode('utf-8', errors='replace')
    dead = []
    for client in _tcp_clients:
        try:
            client.sendall(data)
        except Exception:
            dead.append(client)
    for client in dead:
        try:
            client.close()
        except Exception:
            pass
        if client in _tcp_clients:
            _tcp_clients.remove(client)


def start_tcp_console(port: int = TCP_CONSOLE_PORT):
    """Start TCP console streaming"""
    global _tcp_server
    try:
        _tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _tcp_server.bind(('0.0.0.0', port))
        _tcp_server.listen(5)
        print(f"  Console stream: nc <ip> {port}")
    except Exception as e:
        logger.warning(f"Failed to start TCP console: {e}")


def stop_tcp_console():
    """Stop TCP console"""
    global _tcp_server
    if _tcp_server:
        try:
            _tcp_server.close()
        except Exception:
            pass
        _tcp_server = None


_server_thread = None


def start_web_server(
    get_state: Callable[[], Dict[str, Any]],
    set_setpoint: Callable[[int], bool],
    toggle_dry_run: Callable[[], bool],
    set_limits: Callable[[int, int], Dict[str, int]],
    toggle_ess: Callable[[], Dict[str, Any]],
    set_loop_interval: Callable[[float], float],
    ha: Any,
    host: str = '0.0.0.0',
    port: int = 8080,
    ssl_cert: str = None,
    ssl_key: str = None
):
    """Start FastAPI server in background thread"""
    global state_getter, setpoint_setter, dry_run_toggler, limits_setter
    global ess_mode_toggler, loop_interval_setter, ha_client, _server_thread
    
    state_getter = get_state
    setpoint_setter = set_setpoint
    dry_run_toggler = toggle_dry_run
    limits_setter = set_limits
    ess_mode_toggler = toggle_ess
    loop_interval_setter = set_loop_interval
    ha_client = ha
    
    def run_server():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        config = uvicorn.Config(
            app, host=host, port=port,
            ssl_certfile=ssl_cert if ssl_cert else None,
            ssl_keyfile=ssl_key if ssl_key else None,
            log_level="warning"
        )
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())
    
    import threading
    _server_thread = threading.Thread(target=run_server, daemon=True)
    _server_thread.start()
    
    proto = "https" if ssl_cert else "http"
    print(f"  Web server: {proto}://{host}:{port} (FastAPI + WebSocket)")


def stop_web_server():
    """Stop web server"""
    pass  # Daemon thread will stop with main process
