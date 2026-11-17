"""Constants for LiAuto CLI integration."""

from __future__ import annotations

DOMAIN = "licli"

CONF_MODE = "mode"
CONF_HOST = "host"
CONF_TOKEN = "token"
CONF_ACTIVATION_CODE = "activation_code"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SCAN_PROFILE = "scan_profile"
CONF_DRIVE_FREQUENT = "drive_frequent"

MODE_HTTP = "http"
MODE_LOCAL = "local"

# Polling interval is configured as a "profile" = a multiplier of a base
# interval. "normal" is 1x = 4 minutes; the others scale from that base.
DEFAULT_SCAN_INTERVAL = 600  # legacy raw-seconds fallback (unused by default)
DEFAULT_SCAN_PROFILE = "normal"
SCAN_BASE_INTERVAL = 240  # seconds; normal (1x) = 4 min
SCAN_PROFILES: dict[str, float] = {
    "frequent": 0.25,
    "fast": 0.5,
    "normal": 1.0,
    "slow": 2.0,
    "slowest": 4.0,
}
DEFAULT_HTTP_PORT = 18001


def scan_interval_seconds(profile: str | None) -> int:
    """Return the poll interval (seconds) for a scan profile key."""
    factor = SCAN_PROFILES.get(
        profile or DEFAULT_SCAN_PROFILE, SCAN_PROFILES[DEFAULT_SCAN_PROFILE]
    )
    return int(round(SCAN_BASE_INTERVAL * factor))


# "Frequent while driving": when enabled, poll every DRIVE_INTERVAL seconds
# whenever any vehicle's gear is not P (i.e. R/N/D); otherwise use the profile.
DEFAULT_DRIVE_FREQUENT = True
DRIVE_INTERVAL = 60  # seconds
MOVING_GEARS = frozenset({"R", "N", "D"})

# Control actions that require `-yes` in non-interactive mode (CLI force-confirms
# them). Per the liauto CLI reference only unlock and trunk are confirm-required;
# everything else (lock/find/wake/ac/seat-vent/seat-heat/wheel-heat/window/result)
# must NOT receive -yes. New actions: probe real syntax first, then add here if
# the CLI reports "confirmation required in non-interactive mode (use -yes)".
CONFIRM_ACTIONS = frozenset({"unlock", "trunk"})

# Parking photos (requires liauto>=0.1.2b0).
#   `licli photos <vin> --json` -> {"photos": [{"name","url"}], "picTime", ...}
# After the vehicle transitions to all-doors-locked, re-pull photos once per
# delay, so the parking shots are captured after the car has settled.
PHOTOS_SNAPSHOT_DELAYS = (30, 60)

# Photo names as returned by `licli photos`.
PHOTO_TOP = "picInTop"
# Grid order (left→right, top→bottom): front / rear / right / left.
PHOTO_QUAD = ("picInFront", "picInRear", "picInRight", "picInLeft")
IMAGE_CONTENT_TYPE = "image/jpeg"

COORDINATOR = "coordinator"
CLIENT = "client"

ATTR_VIN = "vin"
ATTR_MODEL = "model"
ATTR_PLATE = "plate"
ATTR_NICKNAME = "nickname"
ATTR_PIC_TIME = "pic_time"


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
    {"field": "gear", "slug": "gear", "device_class": "enum", "unit": None, "state_class": None, "options": ["P", "R", "N", "D", "unknown"]},
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

# Parking image entities. `top` = the single top view, `surround` = the four
# single-camera views (front/rear/left/right) merged into one 2x2 image.
# Source: `licli photos <vin> --json`.
IMAGE_SPECS: tuple[dict, ...] = (
    {"kind": "top", "slug": "parking_top"},
    {"kind": "surround", "slug": "parking_surround"},
)

# Buttons.
BUTTON_SPECS: tuple[dict, ...] = (
    {"action": "find", "slug": "find"},
    {"action": "wake", "slug": "wake"},
)

LOCK_SLUG = "door"
TRUNK_SLUG = "trunk"
CLIMATE_SLUG = "ac"
TRACKER_SLUG = "location"
