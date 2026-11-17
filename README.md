# LiAuto integration for Home Assistant

Home Assistant custom integration for LiAuto vehicles via [licli](https://pypi.org/project/liauto).

## Features

- Two connection modes: Local CLI (`uvx liauto`) or HTTP API (`licli serve`)
- Vehicle status: battery, range, mileage, air conditioning, door state
- Remote control: door lock, air conditioning, find car, wake up
- GPS tracking: live location
- Multiple vehicles: every vehicle on the account is detected automatically

## Installation

### Manual

```bash
cd config/custom_components
unzip licli.zip
```

Restart Home Assistant.

## Configuration

Settings > Devices & Services > Add Integration > **LiAuto CLI**

### Mode 1: Local CLI

Configuration:

- **Activation code**: `eyJ...` (your `LICLI_CODE`)

- **Token JSON**: Find it in browser's F12 dev tools.
  <img width="700" alt="licli json token" src="https://github.com/user-attachments/assets/67f6dd3c-5da0-4740-857f-65f3084ebf32" />

### Mode 2: HTTP API

Requires a running `licli serve` or [deploy using Docker](https://pypi.org/project/liauto/#user-content-docker-compose-deployment):

```bash
export LICLI_CODE=<your activation code>
licli serve --addr 0.0.0.0:18001 --allow-control
```

Configuration:

- **Host**: `http://192.168.x.x:18001`
- **Token**: optional, only if `licli serve` was started with `--token`


## Activation code

Running `licli` requires a valid activation code, bound to a VIN. To get a code, message the Telegram bot [@licli_bot](https://t.me/licli_bot).

## Entities

Entity IDs follow `sensor.{vin_prefix}_{vin_suffix}_{slug}`, for example
`sensor.lsvab2_123456_battery`. The table below lists the slugs.

| Entity | Description |
|--------|-------------|
| `sensor.*_battery` | Battery percentage |
| `sensor.*_batt_endurance` | Electric-only range, km |
| `sensor.*_fuel_endurance` | Fuel range, km |
| `sensor.*_endurance` | Total range, km |
| `sensor.*_mileage` | Odometer, km |
| `sensor.*_ad_mileage` | Mileage driven on assisted driving, km |
| `sensor.*_gear` | Gear position (P/R/N/D) |
| `sensor.*_indoor_temp` | Cabin temperature |
| `sensor.*_outdoor_temp` | Outside temperature |
| `sensor.*_air_quality` | Cabin air quality |
| `sensor.*_charging_status` | Charging state |
| `sensor.*_tire_*_pressure` | Tyre pressure (FL/FR/RL/RR), kPa |
| `device_tracker.*_location` | GPS location |
| `lock.*_door` | Door lock |
| `climate.*_ac` | Air conditioning |
| `button.*_find` | Flash lights and honk |
| `button.*_wake` | Wake the vehicle |
| `switch.*_trunk` | Trunk open/close |
| `binary_sensor.*_online` | Online state |
| `binary_sensor.*_door_*` | Door open state |
| `image.*_parking_top` | Parking top view |
| `image.*_parking_surround` | Parking surround view (2x2 grid) |

## Debugging

```yaml
logger:
  logs:
    custom_components.licli: debug
```
