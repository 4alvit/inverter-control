#!/usr/bin/env python3
"""
Home Assistant Integration
API access with caching and fallback for unreliable connections
"""

import requests
import threading
import time
import logging
from typing import Dict, Any, Optional
from config import (
    HA_URL, HA_TOKEN, HA_TIMEOUT, HA_POLL_INTERVAL,
    HA_SENSORS, HA_BOOLEANS, HA_BINARY_SENSORS,
    HA_DUMP_LOADS, HA_WATER_VALVE, HA_PUMP_SWITCH, VUE_SENSORS
)

logger = logging.getLogger('inverter-control')


class HomeAssistantClient:
    """
    Home Assistant API client with caching and fallback.
    Runs polling in background thread.
    Uses last known values when HA is unreachable.
    """
    
    def __init__(self):
        self._headers = {
            "Authorization": f"Bearer {HA_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Cached values (persist until HA reconnects)
        self._sensors: Dict[str, Any] = {k: 0 for k in HA_SENSORS}
        self._vue_sensors: Dict[str, Any] = {k: 0 for k in VUE_SENSORS}
        self._booleans: Dict[str, bool] = {k: False for k in HA_BOOLEANS}
        self._binary_sensors: Dict[str, bool] = {k: False for k in HA_BINARY_SENSORS}
        self._water_valve: bool = False
        self._pump_switch: bool = False
        
        # Connection status
        self._connected = False
        self._last_update = 0
        self._last_error = ""
        self._last_error_log = 0  # Throttle error logging
        
        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self):
        """Start background polling thread"""
        if self._running:
            return
        
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
    
    @property
    def uptime(self) -> int:
        """Return HA poller uptime in seconds"""
        if hasattr(self, '_start_time'):
            return int(time.time() - self._start_time)
        return 0
    
    def stop(self):
        """Stop background polling"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def _get_state(self, entity_id: str) -> Optional[str]:
        """Get entity state from HA"""
        try:
            response = requests.get(
                f"{HA_URL}/api/states/{entity_id}",
                headers=self._headers,
                timeout=HA_TIMEOUT
            )
            if response.status_code == 200:
                return response.json().get('state')
        except:
            pass
        return None
    
    def _parse_numeric(self, value: str, default: Any = 0) -> Any:
        """Parse numeric value, handle 'unavailable', 'unknown', etc."""
        if value in (None, 'unavailable', 'unknown', 'None', ''):
            return default
        try:
            # Try int first
            if '.' not in str(value):
                return int(value)
            return float(value)
        except:
            return default
    
    def _poll_loop(self):
        """Background polling loop"""
        while self._running:
            try:
                self._poll_all()
                self._connected = True
                self._last_update = time.time()
                self._last_error = ""
            except Exception as e:
                self._connected = False
                self._last_error = str(e)
                # Throttle error logging to once per minute
                now = time.time()
                if now - self._last_error_log > 60:
                    logger.warning(f"HA poll failed: {e}")
                    self._last_error_log = now
            
            time.sleep(HA_POLL_INTERVAL)
    
    def _poll_all(self):
        """Poll all entities from HA"""
        # Use template API for batch fetch (much faster)
        template = self._build_template()
        
        try:
            response = requests.post(
                f"{HA_URL}/api/template",
                headers=self._headers,
                json={"template": template},
                timeout=HA_TIMEOUT
            )
            
            if response.status_code != 200:
                raise Exception(f"HA API error: {response.status_code}")
            
            data = response.json()
            if not isinstance(data, dict):
                raise Exception("Invalid response format")
            
            with self._lock:
                # Parse sensors
                for key in HA_SENSORS:
                    if key in data:
                        self._sensors[key] = self._parse_numeric(data[key])
                
                # Parse VUE sensors
                for key in VUE_SENSORS:
                    if key in data:
                        self._vue_sensors[key] = self._parse_numeric(data[key])
                
                # Parse booleans
                for key in HA_BOOLEANS:
                    if key in data:
                        self._booleans[key] = data[key] == 'on'
                
                # Parse binary sensors
                for key in HA_BINARY_SENSORS:
                    if key in data:
                        self._binary_sensors[key] = data[key] == 'on'
                
                # Water valve
                if 'water_valve' in data:
                    self._water_valve = data['water_valve'] == 'on'
                
                # Pump switch
                if 'pump_switch' in data:
                    self._pump_switch = data['pump_switch'] == 'on'
                    
        except requests.exceptions.Timeout:
            raise Exception("HA timeout")
        except requests.exceptions.ConnectionError:
            raise Exception("HA connection failed")
    
    def _build_template(self) -> str:
        """Build Jinja2 template for batch fetch"""
        parts = ['{']
        
        # Sensors
        for key, entity in HA_SENSORS.items():
            parts.append(f'  "{key}": "{{{{ states("{entity}") }}}}",')
        
        # VUE sensors
        for key, entity in VUE_SENSORS.items():
            parts.append(f'  "{key}": "{{{{ states("{entity}") }}}}",')
        
        # Booleans
        for key, entity in HA_BOOLEANS.items():
            parts.append(f'  "{key}": "{{{{ states("{entity}") }}}}",')
        
        # Binary sensors
        for key, entity in HA_BINARY_SENSORS.items():
            parts.append(f'  "{key}": "{{{{ states("{entity}") }}}}",')
        
        # Water valve and pump
        parts.append(f'  "water_valve": "{{{{ states("{HA_WATER_VALVE}") }}}}",')
        parts.append(f'  "pump_switch": "{{{{ states("{HA_PUMP_SWITCH}") }}}}"')
        
        parts.append('}')
        return '\n'.join(parts)
    
    # === Public API ===
    
    @property
    def connected(self) -> bool:
        return self._connected
    
    @property
    def last_update(self) -> float:
        return self._last_update
    
    @property
    def last_error(self) -> str:
        return self._last_error
    
    def get_sensor(self, key: str, default: Any = 0) -> Any:
        """Get cached sensor value"""
        with self._lock:
            return self._sensors.get(key, default)
    
    def get_vue_sensor(self, key: str, default: Any = 0) -> Any:
        """Get cached VUE sensor value"""
        with self._lock:
            return self._vue_sensors.get(key, default)
    
    def get_all_vue_sensors(self) -> Dict[str, Any]:
        """Get copy of all VUE sensor values"""
        with self._lock:
            return dict(self._vue_sensors)
    
    def get_boolean(self, key: str) -> bool:
        """Get cached boolean value"""
        with self._lock:
            return self._booleans.get(key, False)
    
    def get_binary_sensor(self, key: str) -> bool:
        """Get cached binary sensor value"""
        with self._lock:
            return self._binary_sensors.get(key, False)
    
    @property
    def water_valve_on(self) -> bool:
        with self._lock:
            return self._water_valve
    
    @property
    def pump_switch_on(self) -> bool:
        with self._lock:
            return self._pump_switch
    
    def get_all_sensors(self) -> Dict[str, Any]:
        """Get copy of all sensor values"""
        with self._lock:
            return dict(self._sensors)
    
    def get_all_booleans(self) -> Dict[str, bool]:
        """Get copy of all boolean values"""
        with self._lock:
            return dict(self._booleans)
    
    # === Control Methods ===
    
    def toggle_entity(self, entity_id: str) -> bool:
        """Toggle a switch or input_boolean"""
        try:
            domain = entity_id.split('.')[0]
            response = requests.post(
                f"{HA_URL}/api/services/{domain}/toggle",
                headers=self._headers,
                json={"entity_id": entity_id},
                timeout=HA_TIMEOUT
            )
            return response.status_code == 200
        except:
            return False
    
    def turn_on(self, entity_id: str) -> bool:
        """Turn on a switch or light"""
        try:
            domain = entity_id.split('.')[0]
            service = 'turn_on'
            response = requests.post(
                f"{HA_URL}/api/services/{domain}/{service}",
                headers=self._headers,
                json={"entity_id": entity_id},
                timeout=HA_TIMEOUT
            )
            return response.status_code == 200
        except:
            return False
    
    def turn_off(self, entity_id: str) -> bool:
        """Turn off a switch or light"""
        try:
            domain = entity_id.split('.')[0]
            service = 'turn_off'
            response = requests.post(
                f"{HA_URL}/api/services/{domain}/{service}",
                headers=self._headers,
                json={"entity_id": entity_id},
                timeout=HA_TIMEOUT
            )
            return response.status_code == 200
        except:
            return False
    
    def control_dump_loads(self, turn_on: bool) -> int:
        """Control all dump loads for minimize_charging. Returns count of changed."""
        changed = 0
        for entity in HA_DUMP_LOADS:
            if turn_on:
                if self.turn_on(entity):
                    changed += 1
            else:
                if self.turn_off(entity):
                    changed += 1
        return changed


# Singleton instance
_ha_client: Optional[HomeAssistantClient] = None

def get_ha() -> HomeAssistantClient:
    """Get or create HA client"""
    global _ha_client
    if _ha_client is None:
        _ha_client = HomeAssistantClient()
        _ha_client.start()
    return _ha_client
