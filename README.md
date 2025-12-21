# Petlibro Local Home Assistant Integration

A Home Assistant custom component for controlling Petlibro PLAF301 pet feeders via local MQTT.

## Features

- 🐱 Control Petlibro PLAF301 feeder locally (no cloud required)
- 🚪 Open/close barn door
- 🍖 Dispense food manually
- 🔋 Battery level monitoring
- 📊 Status tracking (empty, clogged, dispensing)
- 🔄 Automatic state updates

## Requirements

- Home Assistant 2023.7.3 or newer
- MQTT broker (Mosquitto recommended)
- Petlibro PLAF301 feeder configured for local MQTT

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL
6. Install "Petlibro Local"
7. Restart Home Assistant

### Manual Installation

1. Copy the `petlibro_local_ha` folder to your `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Petlibro Local"
4. Enter your device information:
   - **Serial Number**: Your device's serial number (found on the device or app)
   - **Device Name**: Friendly name for the device (optional)

## Development & Testing

### Docker Testing Environment

A complete Docker setup is provided for testing:

```bash
# Make setup script executable
chmod +x setup.sh

# Run setup
./setup.sh

# Start services (Home Assistant + MQTT broker)
docker-compose up -d

# View logs
docker-compose logs -f homeassistant

# Stop services
docker-compose down
```

**Test Credentials:**

- Username: `test`
- Password: `test`
- Home Assistant: <http://localhost:8123>
- MQTT Broker: localhost:1883

### Project Structure

```
petlibro_local_ha/
├── __init__.py              # Integration setup
├── config_flow.py           # Configuration UI
├── const.py                 # Constants and enums
├── coordinator.py           # Data update coordinator
├── ha_plaf301.py           # Device handler
├── manifest.json           # Integration metadata
├── message_data.py         # MQTT message structures
├── strings.json            # UI translations
└── vacuum.py               # Vacuum platform entity
```

## Key Improvements in This Version

1. **Async Safety**: All MQTT operations are properly async
2. **Better Error Handling**: Comprehensive exception handling throughout
3. **Proper Cleanup**: Resources are cleaned up on unload
4. **State Management**: Cleaner state tracking and updates
5. **Type Hints**: Full type hints for better IDE support
6. **Logging**: Better logging for debugging
7. **Validation**: Serial number format validation
8. **Options Flow**: Configurable scan interval
9. **Bug Fixes**: Fixed bitwise OR bug and other issues

## Usage

The feeder appears as a "vacuum" entity in Home Assistant (this allows using the door open/close as docking/undocking):

- **Start**: Dispense food (1 portion)
- **Return to Base**: Toggle barn door
- **Battery Level**: Shows device battery percentage
- **Status**: Shows current activity (idle, cleaning/dispensing, docked/door open, error)

### Attributes

The entity provides additional attributes:

- `is_door_open`: Whether the barn door is open
- `is_dispensing`: Whether food is currently being dispensed
- `is_empty`: Whether the grain storage is empty
- `is_clogged`: Whether the grain outlet is clogged
- `error_code`: Current error code (empty, clogged, or none)
- `last_heartbeat`: Timestamp of last heartbeat from device

## Troubleshooting

### Device Not Responding

1. Check MQTT broker is running and accessible
2. Verify device is connected to same MQTT broker
3. Check logs: **Settings** → **System** → **Logs**
4. Verify serial number is correct

### State Not Updating

1. Check the scan interval in integration options
2. Verify MQTT topics are correct for your device model
3. Enable debug logging for more details

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.petlibro_local_ha: debug
```

## MQTT Topics

The integration uses the following topic structure:

- Events: `dl/PLAF301/{SN}/device/event/post`
- Control: `dl/PLAF301/{SN}/device/service/sub`
- Heartbeat: `dl/PLAF301/{SN}/device/heart/post`

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Credits

Created by @gregmolskow
