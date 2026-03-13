# BMW E90 320i N46B20B – ECU Diagnostics & Data Logger

A comprehensive Windows-based diagnostic and data logging tool for the **BMW E90 320i** equipped with the **N46B20B** 2.0 L 4-cylinder Valvetronic engine (Siemens **MSV70** ECU).

Built around the **PYDABAUS** (Python Diagnostic Automation Bridge / Abstraction Utility Service) layer, which provides **ISTA+** and **EDDIBAS**-compatible parameter reading over **UDS on D-CAN** (500 kbps).

---

## Screenshot

![BMW E90 Diagnostics Dashboard](https://github.com/user-attachments/assets/cb7759ee-4893-45e3-89b8-3a6767daa277)

*Live dashboard in demo mode – all 127 ECU parameters displayed as real-time tiles.*

---

## Features

| Feature | Description |
|---|---|
| **ISTA-style GUI dashboard** | Dark-theme graphical interface with live sensor tiles, sensor selection panel, and CSV recording controls |
| **Full parameter catalogue** | **127 ECU parameters** covering every major subsystem |
| **Interactive selection** | Log **all** parameters, filter by keyword, or pick **individual** parameters via checkboxes |
| **Real-time dashboard** | Values refresh every 250 ms with colour-coded live tile display |
| **CSV recording** | One-click start/stop recording to a timestamped CSV file |
| **Sensor availability test** | Tests all 127 sensors; logs missing ones as errors for review |
| **Offline demo mode** | Test the tool without hardware using simulated ECU data |
| **Auto-detect serial port** | Automatically finds BMW K+DCAN / FTDI cables on Windows |
| **Install script** | Creates a desktop shortcut; installs missing packages automatically |
| **Multiple CAN interfaces** | PCAN, Kvaser, Vector, IXXAT, SocketCAN, SLCAN/K+DCAN |

### Parameter categories

- Engine Speed & Load (RPM, torque, load)
- Temperatures (coolant, oil, intake air, exhaust, ambient, cylinder head)
- Fuel System (trims, injector pulse widths, lambda, fuel rate, fuel level)
- Ignition System (timing, knock retard, misfire counters, dwell time)
- Air System (MAF, MAP, throttle, pedal position, idle control, barometric pressure)
- VANOS (intake/exhaust camshaft angles and solenoid duty)
- Valvetronic (eccentric shaft position, motor current, valve lift)
- Oxygen Sensors (wideband lambda, narrowband voltage, heater status, catalyst efficiency)
- Vehicle Speed (wheel speeds, gear, cruise control)
- Electrical (battery voltage, alternator, starter current, ECU supply)
- Emissions (EVAP purge, secondary air, EGR)
- Cooling System (fan speed, thermostat, water pump)
- Crank & Cam Sensors (sync status, camshaft positions)
- Diagnostics (DTC count, MIL status, ECU versions, monitor status)
- Oil System (pressure, level, condition, service counter)
- Climate (AC compressor, refrigerant pressure, compressor torque)
- Chassis (steering angle, brake pressure, yaw rate, lateral/longitudinal acceleration)

---

## Requirements

### Hardware

- **BMW E90 320i** (2005–2011) with N46B20B engine and MSV70 ECU
- **Diagnostic interface** – one of:
  - BMW INPA K+DCAN USB cable (FTDI-based, most common)
  - BMW ICOM (A/B/C)
  - PCAN-USB adapter
  - Kvaser Leaf Light / Pro
  - Vector CANcase / VN16xx
  - Any python-can compatible adapter
- Vehicle **ignition ON** (position II) or engine running

### Software

- **Windows 10/11** (also works on Linux/macOS with SocketCAN)
- **Python 3.10+**

### Python packages

```bash
pip install -r requirements.txt
```

Required packages:
- `python-can` – CAN bus communication
- `pyserial` – Serial port detection for K+DCAN cables
- `tkinter` – GUI toolkit (standard library; see `requirements.txt` for OS-specific install notes)

---

## Installation

### Automated (recommended)

```bash
# Linux / macOS
chmod +x install.sh && ./install.sh

# Windows – double-click install.bat
```

The installer:
1. Detects Python 3.10+
2. Installs `python-can` and `pyserial` (upgrades if outdated)
3. Installs `tkinter` if missing (Linux only – built-in on Windows/macOS)
4. Creates a **desktop shortcut** to launch the GUI

---

## Quick start

### GUI Dashboard (recommended)

```bash
# Demo mode – no hardware needed (desktop shortcut also uses this)
python bmw_e90_gui.py --demo

# Real hardware – K+DCAN cable on COM3
python bmw_e90_gui.py --interface kdcan --port COM3

# Real hardware – PCAN adapter
python bmw_e90_gui.py --interface pcan
```

Once the GUI opens:

1. **Select sensors** using the checkboxes in the left panel (use **All** / **None** / filter box)
2. Watch live values update on the dashboard tiles
3. Click **▶ Start Recording** to save data to a CSV file
4. Click **■ Stop Recording** to stop
5. Click **Test Sensors** to probe all 127 ECU parameters and review any that are unavailable

### CLI Tool

```bash
# Interactive mode – lists all parameters and asks what to log
python bmw_e90_diagnostics.py --interface kdcan --port COM3

# Log everything automatically
python bmw_e90_diagnostics.py --interface kdcan --port COM3 --log-all

# Auto-detect serial port
python bmw_e90_diagnostics.py --interface kdcan --log-all

# Demo mode (no hardware needed)
python bmw_e90_diagnostics.py --demo --log-all --duration 10

# Just list all available parameters
python bmw_e90_diagnostics.py --list-params

# Test which sensors respond (logs missing sensors as errors)
python bmw_e90_diagnostics.py --demo --test-sensors
```

### 4. View the log

The output CSV file contains one row per sweep with a timestamp and all selected parameter values:

```
Timestamp,Engine_RPM,Coolant_Temperature,Vehicle_Speed,...
2026-03-11T10:15:00.123,850.0,72.5,0.0,...
2026-03-11T10:15:00.223,855.0,72.6,0.0,...
```

---

## Sensor Availability Test

The tool can probe every sensor in the catalogue and report which ones respond:

```bash
# Via CLI
python bmw_e90_diagnostics.py --demo --test-sensors

# Via GUI
# Click "Test Sensors" in the sensor selection panel
```

Any sensor that does **not** respond is logged as an `ERROR`:

```
[ERROR] SENSOR UNAVAILABLE: Transmission_Oil_Temperature (DID 0x0205) – No response for DID 0x0205
[ERROR] 1 sensor(s) did not respond. Review the log for SENSOR UNAVAILABLE entries.
```

---

## Command-line options

### bmw_e90_gui.py

```
--demo             Run in offline demo mode with simulated ECU data
--interface, -i    CAN interface type (default: pcan)
--channel, -c      CAN channel (default: PCAN_USBBUS1)
--port, -p         Serial port for K+DCAN cable (e.g. COM3)
--bitrate, -b      CAN bus bitrate (default: 500000)
```

### bmw_e90_diagnostics.py

```
Connection:
  --interface, -i   CAN interface type (pcan, kvaser, vector, ixxat, slcan, kdcan, socketcan)
  --channel, -c     CAN channel (default: PCAN_USBBUS1)
  --port, -p        Serial port for K+DCAN cable (e.g. COM3). Auto-detected if omitted
  --bitrate, -b     CAN bus bitrate (default: 500000)

Logging:
  --log-all         Log all available parameters without prompting
  --output, -o      Output CSV file path (default: bmw_log_<timestamp>.csv)
  --rate, -r        Logging interval in milliseconds (default: 100)
  --duration, -d    Logging duration in seconds (default: 0 = unlimited)

Miscellaneous:
  --list-params     Print all available parameters and exit
  --test-sensors    Test which sensors respond; log missing ones as errors
  --demo            Run in offline demo mode with simulated ECU data
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│           GUI Dashboard (tkinter)            │
│  (sensor selection, live tiles, recording)  │
├─────────────────────────────────────────────┤
│              Interactive CLI                 │
│  (parameter selection, live display, CSV)    │
├─────────────────────────────────────────────┤
│             PYDABAUS Layer                   │
│  (batch reads, logging, session management) │
├─────────────────────────────────────────────┤
│          BMWDiagClient (UDS)                │
│  (ReadDataByIdentifier, session control)    │
├─────────────────────────────────────────────┤
│        ISO-TP Transport (ISO 15765-2)       │
│  (single/multi-frame segmentation)          │
├─────────────────────────────────────────────┤
│           python-can / pyserial             │
│  (PCAN, Kvaser, Vector, SLCAN, SocketCAN)   │
└─────────────────────────────────────────────┘
              │
              ▼
    ┌─────────────────┐
    │  BMW E90 OBD-II  │
    │   D-CAN 500kbps  │
    │   MSV70 DME ECU  │
    └─────────────────┘
```

---

## License

MIT
