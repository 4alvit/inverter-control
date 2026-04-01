# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - 2026-03-29

### Added
- TCP console streaming on port 9999 with ANSI color support
- `commit.sh` and `release.sh` helper scripts
- Additional badges in README

## [1.3.0] - 2026-03-28

### Added
- Home section with Recliner, Garage, Laundry controls
- Pending button state (black) until HA update
- Washer/Dryer sections with power/pause controls
- Large power values formatted as kW (e.g., 9.5kW)
- Dishwasher running time display

### Changed
- Merged Laundry section into Home section
- Improved button state handling

### Fixed
- Toggle buttons not responding
- DRY and ESS mode button colors
- Duration parsing for HH:MM:SS format

## [1.2.0] - 2026-03-27

### Added
- Optional EV, Water, Home Assistant sections
- Feature flags in config.py
- HTTP session pooling for HA
- Circuit breaker pattern for HA polling
- Graceful shutdown handling
- Periodic garbage collection

### Changed
- Improved 24/7 reliability
- Better error handling throughout

## [1.1.0] - 2026-03-26

### Added
- HTTPS support with SSL certificates
- Loop interval control in web UI
- Uptime display in footer
- Power limits override in web UI

### Changed
- Improved web interface design
- Better mobile responsiveness

## [1.0.0] - 2026-03-25

### Added
- Initial release
- Grid-zero feed-in control
- Split-phase compensation
- Web dashboard with real-time graphs
- Multiple operating modes
- Home Assistant integration
- D-Bus communication with Victron

[1.3.1]: https://github.com/victron-venus/inverter-control/releases/tag/v1.3.1
[1.3.0]: https://github.com/victron-venus/inverter-control/releases/tag/v1.3.0
[1.2.0]: https://github.com/victron-venus/inverter-control/releases/tag/v1.2.0
[1.1.0]: https://github.com/victron-venus/inverter-control/releases/tag/v1.1.0
[1.0.0]: https://github.com/victron-venus/inverter-control/releases/tag/v1.0.0
