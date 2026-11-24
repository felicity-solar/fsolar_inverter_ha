# FSolar Inverter HA

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)
[![Release](https://img.shields.io/github/v/release/felicity-solar/fsolar_inverter_ha?style=for-the-badge)](https://github.com/felicity-solar/fsolar_inverter_ha/releases)
[![Validate](https://github.com/felicity-solar/fsolar_inverter_ha/actions/workflows/validate.yml/badge.svg)](https://github.com/felicity-solar/fsolar_inverter_ha/actions/workflows/validate.yml)
[![CI](https://github.com/felicity-solar/fsolar_inverter_ha/actions/workflows/ci.yml/badge.svg)](https://github.com/felicity-solar/fsolar_inverter_ha/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge)](LICENSE)

A Home Assistant integration that reads photovoltaic inverter data locally over Modbus TCP.

## Features

- **Local polling**: talks directly to the inverter's Modbus TCP port — no cloud dependency.
- **Built-in simulator**: try the whole integration without hardware by ticking "Use built-in simulator".
- **Single polling source**: all entities share one `DataUpdateCoordinator`, so the device is never queried twice per cycle.
- **UI setup**: add, reconfigure, and adjust the polling interval entirely from the UI — no YAML required.
- **Diagnostics support**: download redacted diagnostics from the integration card for easy troubleshooting.
- **English and Chinese UI**: translations are provided for both languages.

### Entities provided

| Platform | Entities |
| --- | --- |
| Sensor | PV power, Grid power, Load power, Battery power, Battery SOC, Inverter temperature, Work mode, Production today, Total production |
| Number | Power limit (0–100%, config entity) |

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → the three-dot menu in the top right → **Custom repositories**.
2. Add `https://github.com/felicity-solar/fsolar_inverter_ha` with category **Integration**, then confirm.
3. Search for **FSolar Inverter HA** in the HACS integrations list and click **Download**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and search for **FSolar Inverter HA**.

> Minimum Home Assistant version: `2024.11.0`.

### Manual installation

1. Download the latest source from [Releases](https://github.com/felicity-solar/fsolar_inverter_ha/releases).
2. Copy the `custom_components/fsolar_inverter_ha` directory into `custom_components/` in your Home Assistant configuration directory.
3. Restart Home Assistant, then follow step 5 above to add the integration.

## Configuration

The following fields are required when adding the integration:

| Field | Description | Default |
| --- | --- | --- |
| Host | Inverter IP address | `192.168.1.50` |
| Port | Modbus TCP port | `502` |
| Modbus unit ID | Slave unit ID (1–247) | `1` |
| Use built-in simulator | Use the built-in simulator; when enabled, the three fields above are ignored | Off |

After setup, use **Configure** on the integration card to change the polling interval (5–3600 seconds, default 30 seconds), or **Reconfigure** to switch between a real device and the simulator.

The device serial number (or the simulator identifier) is used as the unique ID, so changing the IP address will not create a duplicate device.

## Diagnostics

Click **Download diagnostics** on the integration card to export a JSON file. Sensitive fields such as the host address and serial numbers are replaced with `**REDACTED**`, so the file is safe to attach to a public issue.

## Development

```bash
python -m pip install -r requirements.txt
python -m compileall -q custom_components
ruff check custom_components
```

Before committing, make sure the hassfest and HACS checks in `.github/workflows/validate.yml` pass. To publish a release, create a Git tag matching the `version` in `manifest.json` (for example `1.0.0`) so HACS can detect the update.

## License

[MIT](LICENSE) © 2026 felicity-solar
