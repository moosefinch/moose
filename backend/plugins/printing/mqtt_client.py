"""
MQTT client for Bambu Labs printer communication.

Connects to the printer's MQTT broker for real-time status monitoring
and command dispatch. Uses paho-mqtt for the MQTT protocol and SSL/TLS
for secure communication.
"""

import asyncio
import json
import logging
import ssl
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Bambu Labs MQTT defaults
MQTT_PORT = 8883
MQTT_USERNAME = "bblp"
FTPS_PORT = 990


class BambuMQTTClient:
    """MQTT client for Bambu Labs printer status and control."""

    def __init__(self, host: str, access_code: str, serial: str = "",
                 port: int = MQTT_PORT):
        self.host = host
        self.access_code = access_code
        self.serial = serial
        self.port = port
        self._client = None
        self._connected = False
        self._state: dict = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    async def connect(self) -> None:
        """Connect to the printer's MQTT broker."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt not installed. Run: pip install paho-mqtt")
            return

        self._loop = asyncio.get_event_loop()

        self._client = mqtt.Client(
            client_id=f"gps_printing_{self.serial[:8] if self.serial else 'client'}",
            protocol=mqtt.MQTTv311,
        )
        self._client.username_pw_set(MQTT_USERNAME, self.access_code)

        # Bambu Labs uses self-signed TLS
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        self._client.tls_set_context(ssl_ctx)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect_async(self.host, self.port)
            self._client.loop_start()
        except Exception as e:
            logger.error("MQTT connection failed: %s", e)

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connect callback."""
        if rc == 0:
            self._connected = True
            logger.info("Connected to Bambu printer MQTT at %s", self.host)
            # Subscribe to status updates
            topic = f"device/{self.serial}/report" if self.serial else "device/#"
            client.subscribe(topic)
            logger.info("Subscribed to %s", topic)

            # Request initial status push
            self._request_status()
        else:
            logger.error("MQTT connection refused: rc=%d", rc)

    def _on_message(self, client, userdata, msg):
        """MQTT message callback — update internal state."""
        try:
            payload = json.loads(msg.payload.decode())
            with self._lock:
                # Bambu sends nested status under "print" key
                if "print" in payload:
                    self._state.update(payload["print"])
                else:
                    self._state.update(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug("Failed to parse MQTT message: %s", e)

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnect callback."""
        self._connected = False
        if rc != 0:
            logger.warning("MQTT disconnected unexpectedly: rc=%d", rc)

    def _request_status(self) -> None:
        """Send a push_all request to get current printer status."""
        if not self._client or not self.serial:
            return
        topic = f"device/{self.serial}/request"
        payload = json.dumps({"pushing": {"command": "pushall"}})
        self._client.publish(topic, payload)

    def publish_command(self, command: dict) -> bool:
        """Publish a command to the printer via MQTT."""
        if not self._client or not self._connected:
            logger.error("Cannot publish: not connected")
            return False
        if not self.serial:
            logger.error("Cannot publish: no serial number configured")
            return False
        topic = f"device/{self.serial}/request"
        try:
            result = self._client.publish(topic, json.dumps(command))
            return result.rc == 0
        except Exception as e:
            logger.error("MQTT publish failed: %s", e)
            return False

    def get_status(self) -> dict:
        """Return the current printer state."""
        with self._lock:
            state = dict(self._state)

        # Extract commonly used fields into a clean summary
        return {
            "connected": self._connected,
            "gcode_state": state.get("gcode_state", "unknown"),
            "mc_percent": state.get("mc_percent", 0),
            "mc_remaining_time": state.get("mc_remaining_time", 0),
            "bed_temper": state.get("bed_temper", 0),
            "bed_target_temper": state.get("bed_target_temper", 0),
            "nozzle_temper": state.get("nozzle_temper", 0),
            "nozzle_target_temper": state.get("nozzle_target_temper", 0),
            "big_fan1_speed": state.get("big_fan1_speed", "0"),
            "big_fan2_speed": state.get("big_fan2_speed", "0"),
            "heatbreak_fan_speed": state.get("heatbreak_fan_speed", "0"),
            "wifi_signal": state.get("wifi_signal", ""),
            "gcode_file": state.get("gcode_file", ""),
            "subtask_name": state.get("subtask_name", ""),
            "layer_num": state.get("layer_num", 0),
            "total_layer_num": state.get("total_layer_num", 0),
            "stg_cur": state.get("stg_cur", 0),
            "raw": state,
        }

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
