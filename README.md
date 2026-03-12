# BMW E90 320i N46B20B – ECU Diagnostics & Data Logger

A comprehensive Windows-based diagnostic and data logging tool for the **BMW E90 320i** equipped with the **N46B20B** 2.0 L 4-cylinder Valvetronic engine (Siemens **MSV70** ECU).

Built around the **PYDABAUS** (Python Diagnostic Automation Bridge / Abstraction Utility Service) layer, which provides **ISTA+** and **EDDIBAS**-compatible parameter reading over **UDS on D-CAN** (500 kbps).

---

## Features

| Feature | Description |
|---|---|
| **Full parameter catalogue** | **120+ ECU parameters** covering every major subsystem |
| **Interactive selection** | Log **all** parameters, pick by **category**, or choose **individual** parameters |
| **Real-time CSV logging** | Timestamped data at configurable rates (default 100 ms) |
| **Live console display** | Key metrics (RPM, coolant, speed, load, throttle) shown in real time |
| **Offline demo mode** | Test the tool without hardware using simulated ECU data |
| **Auto-detect serial port** | Automatically finds BMW K+DCAN / FTDI cables on Windows |
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

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Connect your diagnostic cable

Plug the K+DCAN cable into the OBD-II port (under the dashboard) and the USB end into your Windows PC.

### 3. Run the tool

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
```

### 4. View the log

The output CSV file contains one row per sweep with a timestamp and all selected parameter values:

```
Timestamp,Engine_RPM,Coolant_Temperature,Vehicle_Speed,...
2026-03-11T10:15:00.123,850.0,72.5,0.0,...
2026-03-11T10:15:00.223,855.0,72.6,0.0,...
```

---

## Command-line options

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
  --demo            Run in offline demo mode with simulated ECU data
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
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