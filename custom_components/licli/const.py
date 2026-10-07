"""Constants for LiAuto CLI integration."""

from __future__ import annotations

DOMAIN = "licli"

CONF_MODE = "mode"
CONF_HOST = "host"
CONF_TOKEN = "token"
CONF_ACTIVATION_CODE = "activation_code"
CONF_SCAN_INTERVAL = "scan_interval"

MODE_HTTP = "http"
MODE_LOCAL = "local"

DEFAULT_SCAN_INTERVAL = 60
DEFAULT_HTTP_PORT = 18001

COORDINATOR = "coordinator"
CLIENT = "client"

ATTR_VIN = "vin"
ATTR_MODEL = "model"
ATTR_PLATE = "plate"
ATTR_NICKNAME = "nickname"


# --- Entity naming (mechanism B) -------------------------------------------
#   entity_id = <platform>.{vin_sort}_{slug}
#   unique_id = {VIN}-{slug}
#   slug      = translation_key  ->  translations/<lang>.json: entity.<platform>.<slug>.name
def vin_sort(vin: str) -> str:
    """Return the per-vehicle id prefix: VIN[:6] + '_' + VIN[-6:] (lowercased)."""
    v = vin.lower()
    return f"{v[:6]}_{v[-6:]}"


def entity_id_for(platform: str, vin: str, slug: str) -> str:
    """Build the explicit entity_id for a vehicle entity."""
    return f"{platform}.{vin_sort(vin)}_{slug}"


def unique_id_for(vin: str, slug: str) -> str:
    """Build the stable unique_id for a vehicle entity."""
    return f"{vin}-{slug}"


# --- Entity spec tables (single source of truth) ---------------------------

# Sensor entities. `compute` marks a derived value (no single source field).
SENSOR_SPECS: tuple[dict, ...] = (
    {"field": "batteryLevel", "slug": "battery", "device_class": "battery", "unit": "%", "state_class": "measurement"},
    {"field": "electricRange", "slug": "batt_endurance", "device_class": "distance", "unit": "km", "state_class": "measurement"},
    {"field": "fuelRange", "slug": "fuel_endurance", "device_class": "distance", "unit": "km", "state_class": "measurement"},
    {"compute": "endurance", "slug": "endurance", "device_class": "distance", "unit": "km", "state_class": "measurement"},
    {"field": "totalMileage", "slug": "mileage", "device_class": "distance", "unit": "km", "state_class": "total_increasing"},
    {"field": "adMileage", "slug": "ad_mileage", "device_class": "distance", "unit": "km", "state_class": "total_increasing"},
    {"field": "indoorTemp", "slug": "indoor_temp", "device_class": "temperature", "unit": "°C", "state_class": "measurement"},
    {"field": "outdoorTemp", "slug": "outdoor_temp", "device_class": "temperature", "unit": "°C", "state_class": "measurement"},
    {"field": "airQuality", "slug": "air_quality", "device_class": None, "unit": None, "state_class": "measurement"},
    {
        "field": "chargingStatus",
        "slug": "charging_status",
        "device_class": "enum",
        "unit": None,
        "state_class": None,
        "options": ["charging", "connected", "disconnected", "fault", "full", "unknown"],
    },
)

# Per-door binary sensors.
DOOR_SPECS: tuple[dict, ...] = (
    {"door": "driver", "slug": "door_driver"},
    {"door": "passenger", "slug": "door_passenger"},
    {"door": "rearLeft", "slug": "door_rear_left"},
    {"door": "rearRight", "slug": "door_rear_right"},
    {"door": "trunk", "slug": "door_trunk"},
)

# Online binary sensor.
ONLINE_SPECS: tuple[dict, ...] = (
    {"field": "online", "slug": "online", "device_class": "connectivity"},
)

# Tire-pressure sensors (option B). Each position is a sensor whose state is
# the pressure (kPa); tyre temperature + warning flags ride along as attributes.
# Source: `licli tire <vin> --json` -> data["tires"][pos] = {pressure,temp,...}
TIRE_SPECS: tuple[dict, ...] = (
    {"pos": "frontLeft", "slug": "tire_fl_pressure"},
    {"pos": "frontRight", "slug": "tire_fr_pressure"},
    {"pos": "rearLeft", "slug": "tire_rl_pressure"},
    {"pos": "rearRight", "slug": "tire_rr_pressure"},
)

# Buttons.
BUTTON_SPECS: tuple[dict, ...] = (
    {"action": "find", "slug": "find"},
    {"action": "wake", "slug": "wake"},
    {"action": "trunk", "slug": "trunk", "open": True},
)

LOCK_SLUG = "door"
CLIMATE_SLUG = "ac"
TRACKER_SLUG = "location"
