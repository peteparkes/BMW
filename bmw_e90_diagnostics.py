#!/usr/bin/env python3
"""
BMW E90 320i N46B20B Engine ECU Diagnostic & Data Logging Tool
================================================================

A comprehensive Windows-based diagnostic and data logging script for the
BMW E90 320i equipped with the N46B20B engine (MSV70 ECU).

Supports connection via:
  - ISTA+ compatible interfaces (ICOM, ENET, K+DCAN cable)
  - EDDIBAS diagnostic protocol
  - PYDABAUS automation layer

Uses BMW-specific UDS (Unified Diagnostic Services) over D-CAN (500 kbps)
to read all available ECU parameters.

Usage:
    python bmw_e90_diagnostics.py [--interface TYPE] [--port PORT] [--log-all]
                                   [--output FILE] [--rate MS]

Requirements:
    - Windows OS with python-can and pyserial
    - BMW-compatible diagnostic interface (INPA K+DCAN cable, ICOM, or ENET)
    - Vehicle ignition ON or engine running

Author:  BMW Diagnostics Project
License: MIT
"""

import argparse
import csv
import ctypes
import datetime
import logging
import os
import platform
import struct
import sys
import textwrap
import time
from collections.abc import Callable

# ---------------------------------------------------------------------------
# Optional CAN / Serial imports – gracefully degrade when not installed so the
# parameter catalogue can still be browsed offline.
# ---------------------------------------------------------------------------
try:
    import can

    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False

try:
    import serial
    import serial.tools.list_ports

    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bmw_diag")

# ---------------------------------------------------------------------------
# BMW Protocol Constants
# ---------------------------------------------------------------------------

# D-CAN bus speed for BMW E90
DCAN_BITRATE = 500000

# UDS Service IDs
UDS_DIAGNOSTIC_SESSION_CONTROL = 0x10
UDS_ECU_RESET = 0x11
UDS_SECURITY_ACCESS = 0x27
UDS_READ_DATA_BY_IDENTIFIER = 0x22
UDS_READ_MEMORY_BY_ADDRESS = 0x23
UDS_INPUT_OUTPUT_CONTROL = 0x2F
UDS_ROUTINE_CONTROL = 0x31
UDS_TESTER_PRESENT = 0x3E
UDS_POSITIVE_RESPONSE_OFFSET = 0x40

# BMW Diagnostic Session Types
SESSION_DEFAULT = 0x01
SESSION_EXTENDED = 0x03
SESSION_PROGRAMMING = 0x02
SESSION_DEVELOPMENT = 0x86

# BMW E90 CAN Arbitration IDs
# DME (MSV70) functional request / response addresses on D-CAN
DME_REQUEST_ID = 0x612  # ECU request (Tester -> DME)
DME_RESPONSE_ID = 0x612 + 0x08  # 0x61A  ECU response (DME -> Tester)
FUNCTIONAL_REQUEST_ID = 0x7DF  # OBD-II functional broadcast

# ISO-TP (ISO 15765-2) frame types
ISOTP_SINGLE = 0x00
ISOTP_FIRST = 0x10
ISOTP_CONSECUTIVE = 0x20
ISOTP_FLOW_CONTROL = 0x30

# ---------------------------------------------------------------------------
# N46B20B / MSV70 ECU – Complete Parameter Catalogue
# ---------------------------------------------------------------------------
# Each entry: (did, name, unit, description, decode_func_name, category)
# DID = Data Identifier (UDS 0x22 service)
#
# The catalogue below covers *every* commonly available parameter exposed by
# the Siemens MSV70 DME fitted to the N46B20B 4-cylinder engine in the E90
# 320i (2005-2011).  Parameters are grouped by subsystem.
# ---------------------------------------------------------------------------

# Decode helpers – referenced by name so the catalogue stays serialisable.
# Actual implementations are in the _DECODERS dict further below.

_PARAMETER_CATALOGUE: list[dict] = [
    # ------------------------------------------------------------------
    # CATEGORY: Engine Speed & Load
    # ------------------------------------------------------------------
    {
        "did": 0xF40C,
        "name": "Engine_RPM",
        "unit": "rpm",
        "description": "Engine crankshaft speed",
        "decoder": "rpm",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0x0100,
        "name": "Engine_Speed_Raw",
        "unit": "rpm",
        "description": "Raw engine speed from crankshaft sensor",
        "decoder": "rpm",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0xF404,
        "name": "Engine_Load",
        "unit": "%",
        "description": "Calculated engine load value",
        "decoder": "percent",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0xF443,
        "name": "Absolute_Load",
        "unit": "%",
        "description": "Absolute load value",
        "decoder": "percent16",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0x0101,
        "name": "Engine_Load_Requested",
        "unit": "%",
        "description": "Driver-requested engine load (pedal map)",
        "decoder": "percent",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0x0102,
        "name": "Engine_Torque_Actual",
        "unit": "Nm",
        "description": "Actual engine output torque",
        "decoder": "torque",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0x0103,
        "name": "Engine_Torque_Requested",
        "unit": "Nm",
        "description": "Requested engine torque (from driver / DSC)",
        "decoder": "torque",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0x0104,
        "name": "Engine_Torque_Loss",
        "unit": "Nm",
        "description": "Friction / accessory torque losses",
        "decoder": "torque",
        "category": "Engine Speed & Load",
    },
    {
        "did": 0x0105,
        "name": "Engine_Torque_After_Interventions",
        "unit": "Nm",
        "description": "Torque after DSC / ASC interventions",
        "decoder": "torque",
        "category": "Engine Speed & Load",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Temperatures
    # ------------------------------------------------------------------
    {
        "did": 0xF405,
        "name": "Coolant_Temperature",
        "unit": "°C",
        "description": "Engine coolant temperature",
        "decoder": "temp",
        "category": "Temperatures",
    },
    {
        "did": 0xF40F,
        "name": "Intake_Air_Temperature",
        "unit": "°C",
        "description": "Intake manifold air temperature",
        "decoder": "temp",
        "category": "Temperatures",
    },
    {
        "did": 0x0200,
        "name": "Oil_Temperature",
        "unit": "°C",
        "description": "Engine oil temperature",
        "decoder": "temp16",
        "category": "Temperatures",
    },
    {
        "did": 0x0201,
        "name": "Exhaust_Gas_Temperature_Bank1",
        "unit": "°C",
        "description": "Exhaust gas temperature before catalytic converter – bank 1",
        "decoder": "exhaust_temp",
        "category": "Temperatures",
    },
    {
        "did": 0x0202,
        "name": "Exhaust_Gas_Temperature_Post_Cat_Bank1",
        "unit": "°C",
        "description": "Exhaust gas temperature after catalytic converter – bank 1",
        "decoder": "exhaust_temp",
        "category": "Temperatures",
    },
    {
        "did": 0x0203,
        "name": "Ambient_Air_Temperature",
        "unit": "°C",
        "description": "Ambient (outside) air temperature",
        "decoder": "temp",
        "category": "Temperatures",
    },
    {
        "did": 0x0204,
        "name": "Cylinder_Head_Temperature",
        "unit": "°C",
        "description": "Cylinder head temperature (calculated)",
        "decoder": "temp16",
        "category": "Temperatures",
    },
    {
        "did": 0x0205,
        "name": "Transmission_Oil_Temperature",
        "unit": "°C",
        "description": "Automatic transmission oil temperature (if equipped)",
        "decoder": "temp16",
        "category": "Temperatures",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Fuel System
    # ------------------------------------------------------------------
    {
        "did": 0xF406,
        "name": "Short_Term_Fuel_Trim_Bank1",
        "unit": "%",
        "description": "Short-term fuel trim – bank 1",
        "decoder": "fuel_trim",
        "category": "Fuel System",
    },
    {
        "did": 0xF407,
        "name": "Long_Term_Fuel_Trim_Bank1",
        "unit": "%",
        "description": "Long-term fuel trim – bank 1",
        "decoder": "fuel_trim",
        "category": "Fuel System",
    },
    {
        "did": 0x0300,
        "name": "Fuel_Pressure_Rail",
        "unit": "bar",
        "description": "Fuel rail pressure (direct injection not fitted – port injection)",
        "decoder": "fuel_pressure",
        "category": "Fuel System",
    },
    {
        "did": 0x0301,
        "name": "Fuel_Injector_Pulse_Width_Cyl1",
        "unit": "ms",
        "description": "Injector on-time – cylinder 1",
        "decoder": "injector_pw",
        "category": "Fuel System",
    },
    {
        "did": 0x0302,
        "name": "Fuel_Injector_Pulse_Width_Cyl2",
        "unit": "ms",
        "description": "Injector on-time – cylinder 2",
        "decoder": "injector_pw",
        "category": "Fuel System",
    },
    {
        "did": 0x0303,
        "name": "Fuel_Injector_Pulse_Width_Cyl3",
        "unit": "ms",
        "description": "Injector on-time – cylinder 3",
        "decoder": "injector_pw",
        "category": "Fuel System",
    },
    {
        "did": 0x0304,
        "name": "Fuel_Injector_Pulse_Width_Cyl4",
        "unit": "ms",
        "description": "Injector on-time – cylinder 4",
        "decoder": "injector_pw",
        "category": "Fuel System",
    },
    {
        "did": 0x0305,
        "name": "Fuel_Consumption_Rate",
        "unit": "L/h",
        "description": "Instantaneous fuel consumption",
        "decoder": "fuel_rate",
        "category": "Fuel System",
    },
    {
        "did": 0x0306,
        "name": "Fuel_Level",
        "unit": "%",
        "description": "Fuel tank level",
        "decoder": "percent",
        "category": "Fuel System",
    },
    {
        "did": 0x0307,
        "name": "Lambda_Integrator_Bank1",
        "unit": "",
        "description": "Lambda integrator value – bank 1",
        "decoder": "lambda_int",
        "category": "Fuel System",
    },
    {
        "did": 0x0308,
        "name": "Lambda_Target",
        "unit": "",
        "description": "Target lambda (AFR commanded)",
        "decoder": "lambda_val",
        "category": "Fuel System",
    },
    {
        "did": 0x0309,
        "name": "Lambda_Actual",
        "unit": "",
        "description": "Actual lambda (measured AFR)",
        "decoder": "lambda_val",
        "category": "Fuel System",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Ignition System
    # ------------------------------------------------------------------
    {
        "did": 0xF40E,
        "name": "Ignition_Timing_Advance",
        "unit": "° BTDC",
        "description": "Ignition timing advance angle",
        "decoder": "timing",
        "category": "Ignition System",
    },
    {
        "did": 0x0400,
        "name": "Ignition_Timing_Cyl1",
        "unit": "° BTDC",
        "description": "Individual ignition timing – cylinder 1",
        "decoder": "timing",
        "category": "Ignition System",
    },
    {
        "did": 0x0401,
        "name": "Ignition_Timing_Cyl2",
        "unit": "° BTDC",
        "description": "Individual ignition timing – cylinder 2",
        "decoder": "timing",
        "category": "Ignition System",
    },
    {
        "did": 0x0402,
        "name": "Ignition_Timing_Cyl3",
        "unit": "° BTDC",
        "description": "Individual ignition timing – cylinder 3",
        "decoder": "timing",
        "category": "Ignition System",
    },
    {
        "did": 0x0403,
        "name": "Ignition_Timing_Cyl4",
        "unit": "° BTDC",
        "description": "Individual ignition timing – cylinder 4",
        "decoder": "timing",
        "category": "Ignition System",
    },
    {
        "did": 0x0404,
        "name": "Knock_Retard_Cyl1",
        "unit": "°",
        "description": "Knock-induced timing retard – cylinder 1",
        "decoder": "knock_retard",
        "category": "Ignition System",
    },
    {
        "did": 0x0405,
        "name": "Knock_Retard_Cyl2",
        "unit": "°",
        "description": "Knock-induced timing retard – cylinder 2",
        "decoder": "knock_retard",
        "category": "Ignition System",
    },
    {
        "did": 0x0406,
        "name": "Knock_Retard_Cyl3",
        "unit": "°",
        "description": "Knock-induced timing retard – cylinder 3",
        "decoder": "knock_retard",
        "category": "Ignition System",
    },
    {
        "did": 0x0407,
        "name": "Knock_Retard_Cyl4",
        "unit": "°",
        "description": "Knock-induced timing retard – cylinder 4",
        "decoder": "knock_retard",
        "category": "Ignition System",
    },
    {
        "did": 0x0408,
        "name": "Knock_Sensor_Voltage_1",
        "unit": "V",
        "description": "Knock sensor 1 signal voltage",
        "decoder": "voltage",
        "category": "Ignition System",
    },
    {
        "did": 0x0409,
        "name": "Knock_Sensor_Voltage_2",
        "unit": "V",
        "description": "Knock sensor 2 signal voltage",
        "decoder": "voltage",
        "category": "Ignition System",
    },
    {
        "did": 0x040A,
        "name": "Ignition_Coil_Dwell_Time",
        "unit": "ms",
        "description": "Ignition coil charge (dwell) time",
        "decoder": "dwell",
        "category": "Ignition System",
    },
    {
        "did": 0x040B,
        "name": "Misfire_Counter_Cyl1",
        "unit": "count",
        "description": "Misfire event counter – cylinder 1",
        "decoder": "counter16",
        "category": "Ignition System",
    },
    {
        "did": 0x040C,
        "name": "Misfire_Counter_Cyl2",
        "unit": "count",
        "description": "Misfire event counter – cylinder 2",
        "decoder": "counter16",
        "category": "Ignition System",
    },
    {
        "did": 0x040D,
        "name": "Misfire_Counter_Cyl3",
        "unit": "count",
        "description": "Misfire event counter – cylinder 3",
        "decoder": "counter16",
        "category": "Ignition System",
    },
    {
        "did": 0x040E,
        "name": "Misfire_Counter_Cyl4",
        "unit": "count",
        "description": "Misfire event counter – cylinder 4",
        "decoder": "counter16",
        "category": "Ignition System",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Air System / Intake
    # ------------------------------------------------------------------
    {
        "did": 0xF410,
        "name": "MAF_Sensor",
        "unit": "g/s",
        "description": "Mass air flow sensor reading",
        "decoder": "maf",
        "category": "Air System",
    },
    {
        "did": 0xF411,
        "name": "Throttle_Position",
        "unit": "%",
        "description": "Electronic throttle valve position",
        "decoder": "percent",
        "category": "Air System",
    },
    {
        "did": 0xF40B,
        "name": "Intake_Manifold_Pressure",
        "unit": "kPa",
        "description": "Intake manifold absolute pressure (MAP)",
        "decoder": "pressure_kpa",
        "category": "Air System",
    },
    {
        "did": 0x0500,
        "name": "Throttle_Valve_Angle",
        "unit": "°",
        "description": "Throttle plate angle (electronic throttle)",
        "decoder": "angle",
        "category": "Air System",
    },
    {
        "did": 0x0501,
        "name": "Throttle_Valve_Target",
        "unit": "°",
        "description": "Target throttle plate angle",
        "decoder": "angle",
        "category": "Air System",
    },
    {
        "did": 0x0502,
        "name": "Accelerator_Pedal_Position_1",
        "unit": "%",
        "description": "Accelerator pedal sensor 1 position",
        "decoder": "percent",
        "category": "Air System",
    },
    {
        "did": 0x0503,
        "name": "Accelerator_Pedal_Position_2",
        "unit": "%",
        "description": "Accelerator pedal sensor 2 position (redundant)",
        "decoder": "percent",
        "category": "Air System",
    },
    {
        "did": 0x0504,
        "name": "Idle_Speed_Target",
        "unit": "rpm",
        "description": "ECU idle speed target",
        "decoder": "rpm",
        "category": "Air System",
    },
    {
        "did": 0x0505,
        "name": "Idle_Speed_Actual",
        "unit": "rpm",
        "description": "Actual idle speed",
        "decoder": "rpm",
        "category": "Air System",
    },
    {
        "did": 0x0506,
        "name": "Idle_Air_Correction",
        "unit": "%",
        "description": "Idle air control correction factor",
        "decoder": "fuel_trim",
        "category": "Air System",
    },
    {
        "did": 0x0507,
        "name": "Barometric_Pressure",
        "unit": "kPa",
        "description": "Barometric (atmospheric) pressure",
        "decoder": "pressure_kpa",
        "category": "Air System",
    },
    {
        "did": 0x0508,
        "name": "Air_Mass_Per_Stroke",
        "unit": "mg",
        "description": "Air mass per intake stroke",
        "decoder": "air_mass_stroke",
        "category": "Air System",
    },
    # ------------------------------------------------------------------
    # CATEGORY: VANOS (Variable Valve Timing)
    # ------------------------------------------------------------------
    {
        "did": 0x0600,
        "name": "VANOS_Intake_Target",
        "unit": "° CA",
        "description": "VANOS intake camshaft target angle",
        "decoder": "vanos_angle",
        "category": "VANOS",
    },
    {
        "did": 0x0601,
        "name": "VANOS_Intake_Actual",
        "unit": "° CA",
        "description": "VANOS intake camshaft actual angle",
        "decoder": "vanos_angle",
        "category": "VANOS",
    },
    {
        "did": 0x0602,
        "name": "VANOS_Exhaust_Target",
        "unit": "° CA",
        "description": "VANOS exhaust camshaft target angle",
        "decoder": "vanos_angle",
        "category": "VANOS",
    },
    {
        "did": 0x0603,
        "name": "VANOS_Exhaust_Actual",
        "unit": "° CA",
        "description": "VANOS exhaust camshaft actual angle",
        "decoder": "vanos_angle",
        "category": "VANOS",
    },
    {
        "did": 0x0604,
        "name": "VANOS_Intake_Solenoid_Duty",
        "unit": "%",
        "description": "VANOS intake solenoid duty cycle",
        "decoder": "percent",
        "category": "VANOS",
    },
    {
        "did": 0x0605,
        "name": "VANOS_Exhaust_Solenoid_Duty",
        "unit": "%",
        "description": "VANOS exhaust solenoid duty cycle",
        "decoder": "percent",
        "category": "VANOS",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Valvetronic (Variable Valve Lift – N46 specific)
    # ------------------------------------------------------------------
    {
        "did": 0x0650,
        "name": "Valvetronic_Eccentric_Shaft_Angle",
        "unit": "°",
        "description": "Valvetronic eccentric shaft position",
        "decoder": "vt_angle",
        "category": "Valvetronic",
    },
    {
        "did": 0x0651,
        "name": "Valvetronic_Eccentric_Shaft_Target",
        "unit": "°",
        "description": "Valvetronic eccentric shaft target position",
        "decoder": "vt_angle",
        "category": "Valvetronic",
    },
    {
        "did": 0x0652,
        "name": "Valvetronic_Motor_Current",
        "unit": "A",
        "description": "Valvetronic stepper motor current draw",
        "decoder": "current",
        "category": "Valvetronic",
    },
    {
        "did": 0x0653,
        "name": "Valvetronic_Motor_Duty",
        "unit": "%",
        "description": "Valvetronic motor PWM duty cycle",
        "decoder": "percent",
        "category": "Valvetronic",
    },
    {
        "did": 0x0654,
        "name": "Valvetronic_Valve_Lift",
        "unit": "mm",
        "description": "Calculated intake valve lift",
        "decoder": "valve_lift",
        "category": "Valvetronic",
    },
    {
        "did": 0x0655,
        "name": "Valvetronic_Reference_Position",
        "unit": "°",
        "description": "Valvetronic reference (home) position learned value",
        "decoder": "vt_angle",
        "category": "Valvetronic",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Oxygen Sensors / Lambda
    # ------------------------------------------------------------------
    {
        "did": 0xF414,
        "name": "O2_Sensor_Voltage_B1S1",
        "unit": "V",
        "description": "Oxygen sensor voltage – bank 1 sensor 1 (pre-cat)",
        "decoder": "o2_voltage",
        "category": "Oxygen Sensors",
    },
    {
        "did": 0xF418,
        "name": "O2_Sensor_Voltage_B1S2",
        "unit": "V",
        "description": "Oxygen sensor voltage – bank 1 sensor 2 (post-cat)",
        "decoder": "o2_voltage",
        "category": "Oxygen Sensors",
    },
    {
        "did": 0x0700,
        "name": "Wideband_Lambda_B1S1",
        "unit": "λ",
        "description": "Wideband lambda value – bank 1 sensor 1",
        "decoder": "lambda_val",
        "category": "Oxygen Sensors",
    },
    {
        "did": 0x0701,
        "name": "Wideband_Lambda_Current_B1S1",
        "unit": "mA",
        "description": "Wideband O₂ sensor pump current – bank 1 sensor 1",
        "decoder": "o2_current",
        "category": "Oxygen Sensors",
    },
    {
        "did": 0x0702,
        "name": "Narrowband_Lambda_B1S2",
        "unit": "V",
        "description": "Narrowband O₂ sensor voltage – bank 1 sensor 2 (post-cat)",
        "decoder": "o2_voltage",
        "category": "Oxygen Sensors",
    },
    {
        "did": 0x0703,
        "name": "O2_Sensor_Heater_Status_B1S1",
        "unit": "",
        "description": "O₂ sensor heater status – bank 1 sensor 1 (0=Off 1=On)",
        "decoder": "bool_byte",
        "category": "Oxygen Sensors",
    },
    {
        "did": 0x0704,
        "name": "O2_Sensor_Heater_Status_B1S2",
        "unit": "",
        "description": "O₂ sensor heater status – bank 1 sensor 2 (0=Off 1=On)",
        "decoder": "bool_byte",
        "category": "Oxygen Sensors",
    },
    {
        "did": 0x0705,
        "name": "Catalyst_Efficiency_Bank1",
        "unit": "%",
        "description": "Catalytic converter efficiency – bank 1",
        "decoder": "percent",
        "category": "Oxygen Sensors",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Vehicle Speed & Transmission
    # ------------------------------------------------------------------
    {
        "did": 0xF40D,
        "name": "Vehicle_Speed",
        "unit": "km/h",
        "description": "Vehicle speed (from wheel speed sensors)",
        "decoder": "speed",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0800,
        "name": "Wheel_Speed_FL",
        "unit": "km/h",
        "description": "Front-left wheel speed",
        "decoder": "wheel_speed",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0801,
        "name": "Wheel_Speed_FR",
        "unit": "km/h",
        "description": "Front-right wheel speed",
        "decoder": "wheel_speed",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0802,
        "name": "Wheel_Speed_RL",
        "unit": "km/h",
        "description": "Rear-left wheel speed",
        "decoder": "wheel_speed",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0803,
        "name": "Wheel_Speed_RR",
        "unit": "km/h",
        "description": "Rear-right wheel speed",
        "decoder": "wheel_speed",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0804,
        "name": "Gear_Engaged",
        "unit": "",
        "description": "Currently engaged gear (0=N, 1-6, R)",
        "decoder": "gear",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0805,
        "name": "Clutch_Switch",
        "unit": "",
        "description": "Clutch pedal switch state (0=Released 1=Pressed)",
        "decoder": "bool_byte",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0806,
        "name": "Cruise_Control_Active",
        "unit": "",
        "description": "Cruise control active flag",
        "decoder": "bool_byte",
        "category": "Vehicle Speed",
    },
    {
        "did": 0x0807,
        "name": "Cruise_Control_Set_Speed",
        "unit": "km/h",
        "description": "Cruise control target speed",
        "decoder": "speed",
        "category": "Vehicle Speed",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Electrical System
    # ------------------------------------------------------------------
    {
        "did": 0xF442,
        "name": "Battery_Voltage",
        "unit": "V",
        "description": "Vehicle battery (system) voltage",
        "decoder": "battery_voltage",
        "category": "Electrical",
    },
    {
        "did": 0x0900,
        "name": "Alternator_Target_Voltage",
        "unit": "V",
        "description": "Alternator target charging voltage",
        "decoder": "voltage16",
        "category": "Electrical",
    },
    {
        "did": 0x0901,
        "name": "Alternator_Actual_Voltage",
        "unit": "V",
        "description": "Alternator measured output voltage",
        "decoder": "voltage16",
        "category": "Electrical",
    },
    {
        "did": 0x0902,
        "name": "Alternator_Load_Signal",
        "unit": "%",
        "description": "Alternator electrical load signal (BSD)",
        "decoder": "percent",
        "category": "Electrical",
    },
    {
        "did": 0x0903,
        "name": "Starter_Motor_Current",
        "unit": "A",
        "description": "Starter motor current during cranking",
        "decoder": "current16",
        "category": "Electrical",
    },
    {
        "did": 0x0904,
        "name": "ECU_Supply_Voltage",
        "unit": "V",
        "description": "DME ECU internal supply voltage",
        "decoder": "voltage16",
        "category": "Electrical",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Emissions / Evaporative System
    # ------------------------------------------------------------------
    {
        "did": 0x0A00,
        "name": "EVAP_Purge_Valve_Duty",
        "unit": "%",
        "description": "EVAP canister purge valve duty cycle",
        "decoder": "percent",
        "category": "Emissions",
    },
    {
        "did": 0x0A01,
        "name": "EVAP_System_Pressure",
        "unit": "Pa",
        "description": "EVAP system tank pressure",
        "decoder": "evap_pressure",
        "category": "Emissions",
    },
    {
        "did": 0x0A02,
        "name": "Secondary_Air_Pump_Status",
        "unit": "",
        "description": "Secondary air injection pump relay status (0=Off 1=On)",
        "decoder": "bool_byte",
        "category": "Emissions",
    },
    {
        "did": 0x0A03,
        "name": "Secondary_Air_Mass_Flow",
        "unit": "g/s",
        "description": "Secondary air injection mass flow rate",
        "decoder": "maf",
        "category": "Emissions",
    },
    {
        "did": 0x0A04,
        "name": "EGR_Valve_Position",
        "unit": "%",
        "description": "EGR valve position (if applicable)",
        "decoder": "percent",
        "category": "Emissions",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Cooling System
    # ------------------------------------------------------------------
    {
        "did": 0x0B00,
        "name": "Electric_Fan_Speed",
        "unit": "%",
        "description": "Electric radiator fan speed duty cycle",
        "decoder": "percent",
        "category": "Cooling System",
    },
    {
        "did": 0x0B01,
        "name": "Thermostat_Map_Controlled",
        "unit": "°C",
        "description": "Map-controlled thermostat target temperature",
        "decoder": "temp",
        "category": "Cooling System",
    },
    {
        "did": 0x0B02,
        "name": "Electric_Water_Pump_Speed",
        "unit": "%",
        "description": "Electric water pump speed (if equipped)",
        "decoder": "percent",
        "category": "Cooling System",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Crankshaft / Camshaft Sensors
    # ------------------------------------------------------------------
    {
        "did": 0x0C00,
        "name": "Crankshaft_Sensor_Signal",
        "unit": "",
        "description": "Crankshaft position sensor signal status",
        "decoder": "bool_byte",
        "category": "Crank & Cam Sensors",
    },
    {
        "did": 0x0C01,
        "name": "Camshaft_Intake_Position",
        "unit": "° CA",
        "description": "Intake camshaft position (absolute)",
        "decoder": "cam_angle",
        "category": "Crank & Cam Sensors",
    },
    {
        "did": 0x0C02,
        "name": "Camshaft_Exhaust_Position",
        "unit": "° CA",
        "description": "Exhaust camshaft position (absolute)",
        "decoder": "cam_angle",
        "category": "Crank & Cam Sensors",
    },
    {
        "did": 0x0C03,
        "name": "Engine_Position_Sync_Status",
        "unit": "",
        "description": "Engine crank/cam synchronisation status (0=Not synced 1=Synced)",
        "decoder": "bool_byte",
        "category": "Crank & Cam Sensors",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Fault Codes / Diagnostics
    # ------------------------------------------------------------------
    {
        "did": 0xF401,
        "name": "Monitor_Status_Since_Clear",
        "unit": "",
        "description": "OBD monitor status since DTCs cleared (bit-field)",
        "decoder": "hex32",
        "category": "Diagnostics",
    },
    {
        "did": 0xF41C,
        "name": "OBD_Standard",
        "unit": "",
        "description": "OBD standards this vehicle conforms to",
        "decoder": "raw_byte",
        "category": "Diagnostics",
    },
    {
        "did": 0xF41D,
        "name": "O2_Sensors_Present",
        "unit": "",
        "description": "Bitmask of O₂ sensors present in bank 1",
        "decoder": "hex8",
        "category": "Diagnostics",
    },
    {
        "did": 0xF421,
        "name": "Distance_With_MIL_On",
        "unit": "km",
        "description": "Distance travelled while MIL is illuminated",
        "decoder": "distance16",
        "category": "Diagnostics",
    },
    {
        "did": 0xF431,
        "name": "Distance_Since_Codes_Cleared",
        "unit": "km",
        "description": "Distance travelled since diagnostic trouble codes cleared",
        "decoder": "distance16",
        "category": "Diagnostics",
    },
    {
        "did": 0xF41E,
        "name": "Run_Time_Since_Start",
        "unit": "s",
        "description": "Time since engine start",
        "decoder": "runtime16",
        "category": "Diagnostics",
    },
    {
        "did": 0x0D00,
        "name": "DTC_Count",
        "unit": "",
        "description": "Number of stored diagnostic trouble codes",
        "decoder": "raw_byte",
        "category": "Diagnostics",
    },
    {
        "did": 0x0D01,
        "name": "MIL_Status",
        "unit": "",
        "description": "Malfunction indicator lamp status (0=Off 1=On)",
        "decoder": "bool_byte",
        "category": "Diagnostics",
    },
    {
        "did": 0x0D02,
        "name": "ECU_Hardware_Version",
        "unit": "",
        "description": "DME ECU hardware version string",
        "decoder": "ascii",
        "category": "Diagnostics",
    },
    {
        "did": 0x0D03,
        "name": "ECU_Software_Version",
        "unit": "",
        "description": "DME ECU software version string",
        "decoder": "ascii",
        "category": "Diagnostics",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Oil System
    # ------------------------------------------------------------------
    {
        "did": 0x0E00,
        "name": "Oil_Pressure",
        "unit": "bar",
        "description": "Engine oil pressure",
        "decoder": "oil_pressure",
        "category": "Oil System",
    },
    {
        "did": 0x0E01,
        "name": "Oil_Level",
        "unit": "mm",
        "description": "Engine oil level (electronic sensor)",
        "decoder": "oil_level",
        "category": "Oil System",
    },
    {
        "did": 0x0E02,
        "name": "Oil_Condition",
        "unit": "%",
        "description": "Remaining engine oil life / condition",
        "decoder": "percent",
        "category": "Oil System",
    },
    {
        "did": 0x0E03,
        "name": "Oil_Service_Counter",
        "unit": "km",
        "description": "Distance until next oil service (CBS)",
        "decoder": "distance16",
        "category": "Oil System",
    },
    # ------------------------------------------------------------------
    # CATEGORY: AC / Climate
    # ------------------------------------------------------------------
    {
        "did": 0x0F00,
        "name": "AC_Compressor_Status",
        "unit": "",
        "description": "AC compressor clutch status (0=Off 1=On)",
        "decoder": "bool_byte",
        "category": "Climate",
    },
    {
        "did": 0x0F01,
        "name": "AC_Refrigerant_Pressure",
        "unit": "bar",
        "description": "AC refrigerant high-side pressure",
        "decoder": "ac_pressure",
        "category": "Climate",
    },
    {
        "did": 0x0F02,
        "name": "AC_Compressor_Torque",
        "unit": "Nm",
        "description": "Torque consumed by AC compressor",
        "decoder": "torque_small",
        "category": "Climate",
    },
    # ------------------------------------------------------------------
    # CATEGORY: Steering & Brakes (information via CAN gateway)
    # ------------------------------------------------------------------
    {
        "did": 0x1000,
        "name": "Steering_Angle",
        "unit": "°",
        "description": "Steering wheel angle",
        "decoder": "steering_angle",
        "category": "Chassis",
    },
    {
        "did": 0x1001,
        "name": "Brake_Pedal_Pressed",
        "unit": "",
        "description": "Brake pedal switch state (0=Released 1=Pressed)",
        "decoder": "bool_byte",
        "category": "Chassis",
    },
    {
        "did": 0x1002,
        "name": "Brake_Pressure",
        "unit": "bar",
        "description": "Brake master cylinder pressure",
        "decoder": "brake_pressure",
        "category": "Chassis",
    },
    {
        "did": 0x1003,
        "name": "Yaw_Rate",
        "unit": "°/s",
        "description": "Vehicle yaw rate (from DSC module)",
        "decoder": "yaw_rate",
        "category": "Chassis",
    },
    {
        "did": 0x1004,
        "name": "Lateral_Acceleration",
        "unit": "g",
        "description": "Lateral (sideways) acceleration",
        "decoder": "accel_g",
        "category": "Chassis",
    },
    {
        "did": 0x1005,
        "name": "Longitudinal_Acceleration",
        "unit": "g",
        "description": "Longitudinal (fore/aft) acceleration",
        "decoder": "accel_g",
        "category": "Chassis",
    },
]

# Total parameter count for quick reference
TOTAL_PARAMETER_COUNT = len(_PARAMETER_CATALOGUE)

# ---------------------------------------------------------------------------
# Decoders – convert raw ECU bytes into engineering values.
# ---------------------------------------------------------------------------


def _decode_rpm(data: bytes) -> float:
    """RPM = ((A * 256) + B) / 4"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 4.0


def _decode_percent(data: bytes) -> float:
    """Single-byte percentage: A * 100/255"""
    if not data:
        return 0.0
    return data[0] * 100.0 / 255.0


def _decode_percent16(data: bytes) -> float:
    """Two-byte percentage: ((A*256)+B) * 100/65535"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) * 100.0 / 65535.0


def _decode_temp(data: bytes) -> float:
    """Single-byte temperature: A - 40 °C"""
    if not data:
        return -40.0
    return data[0] - 40.0


def _decode_temp16(data: bytes) -> float:
    """Two-byte temperature: ((A*256)+B)/10 - 40"""
    if len(data) < 2:
        return -40.0
    return ((data[0] << 8) | data[1]) / 10.0 - 40.0


def _decode_exhaust_temp(data: bytes) -> float:
    """Two-byte exhaust gas temp: ((A*256)+B)/10 - 40"""
    return _decode_temp16(data)


def _decode_fuel_trim(data: bytes) -> float:
    """Fuel trim: (A - 128) * 100/128 %"""
    if not data:
        return 0.0
    return (data[0] - 128) * 100.0 / 128.0


def _decode_timing(data: bytes) -> float:
    """Ignition timing: (A - 128) / 2 degrees"""
    if not data:
        return 0.0
    return (data[0] - 128) / 2.0


def _decode_maf(data: bytes) -> float:
    """MAF: ((A*256)+B) / 100 g/s"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_speed(data: bytes) -> float:
    """Vehicle speed: A km/h"""
    if not data:
        return 0.0
    return float(data[0])


def _decode_wheel_speed(data: bytes) -> float:
    """Wheel speed: ((A*256)+B) / 100 km/h"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_voltage(data: bytes) -> float:
    """Sensor voltage: A / 200 * 5 V  (0-5 V range)"""
    if not data:
        return 0.0
    return data[0] * 5.0 / 255.0


def _decode_voltage16(data: bytes) -> float:
    """Two-byte voltage: ((A*256)+B) / 1000 V"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 1000.0


def _decode_battery_voltage(data: bytes) -> float:
    """Battery voltage: A / 10 V (BMW encoding)"""
    if not data:
        return 0.0
    if len(data) >= 2:
        return ((data[0] << 8) | data[1]) / 1000.0
    return data[0] / 10.0


def _decode_pressure_kpa(data: bytes) -> float:
    """Pressure kPa: A (single byte)"""
    if not data:
        return 0.0
    return float(data[0])


def _decode_fuel_pressure(data: bytes) -> float:
    """Fuel rail pressure: ((A*256)+B) * 0.079 bar"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) * 0.079


def _decode_injector_pw(data: bytes) -> float:
    """Injector pulse width: ((A*256)+B) / 1000 ms"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 1000.0


def _decode_fuel_rate(data: bytes) -> float:
    """Fuel rate: ((A*256)+B) / 20 L/h"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 20.0


def _decode_lambda_int(data: bytes) -> float:
    """Lambda integrator: (A - 128) / 128"""
    if not data:
        return 0.0
    return (data[0] - 128) / 128.0


def _decode_lambda_val(data: bytes) -> float:
    """Lambda value: ((A*256)+B) / 32768"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 32768.0


def _decode_o2_voltage(data: bytes) -> float:
    """O2 sensor voltage: A / 200 V (narrowband) or ((A*256)+B)/1000 (wideband)"""
    if len(data) >= 2:
        return ((data[0] << 8) | data[1]) / 1000.0
    if data:
        return data[0] / 200.0
    return 0.0


def _decode_o2_current(data: bytes) -> float:
    """Wideband O2 pump current: ((A*256)+B) / 256 - 128 mA"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 256.0 - 128.0


def _decode_torque(data: bytes) -> float:
    """Engine torque: ((A*256)+B) / 10 - offset Nm"""
    if len(data) < 2:
        return 0.0
    raw = (data[0] << 8) | data[1]
    return raw / 10.0


def _decode_torque_small(data: bytes) -> float:
    """Small torque value: A * 0.5 Nm"""
    if not data:
        return 0.0
    return data[0] * 0.5


def _decode_knock_retard(data: bytes) -> float:
    """Knock retard: A / 4 degrees"""
    if not data:
        return 0.0
    return data[0] / 4.0


def _decode_dwell(data: bytes) -> float:
    """Coil dwell time: ((A*256)+B) / 1000 ms"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 1000.0


def _decode_counter16(data: bytes) -> int:
    """16-bit counter"""
    if len(data) < 2:
        return 0
    return (data[0] << 8) | data[1]


def _decode_distance16(data: bytes) -> int:
    """16-bit distance in km"""
    if len(data) < 2:
        return 0
    return (data[0] << 8) | data[1]


def _decode_runtime16(data: bytes) -> int:
    """16-bit run time in seconds"""
    if len(data) < 2:
        return 0
    return (data[0] << 8) | data[1]


def _decode_vanos_angle(data: bytes) -> float:
    """VANOS angle: ((A*256)+B) / 10 - 50 ° CA"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 10.0 - 50.0


def _decode_vt_angle(data: bytes) -> float:
    """Valvetronic eccentric shaft angle: ((A*256)+B) / 100 °"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_valve_lift(data: bytes) -> float:
    """Valve lift: ((A*256)+B) / 100 mm"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_current(data: bytes) -> float:
    """Current: ((A*256)+B) / 100 A"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_current16(data: bytes) -> float:
    """Current 16-bit: ((A*256)+B) / 10 A"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 10.0


def _decode_angle(data: bytes) -> float:
    """Angle: ((A*256)+B) / 100 degrees"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_oil_pressure(data: bytes) -> float:
    """Oil pressure: A * 3/255 bar"""
    if not data:
        return 0.0
    return data[0] * 3.0 / 255.0


def _decode_oil_level(data: bytes) -> float:
    """Oil level: A mm (signed)"""
    if not data:
        return 0.0
    val = data[0]
    if val > 127:
        val -= 256
    return float(val)


def _decode_evap_pressure(data: bytes) -> float:
    """EVAP pressure: ((A*256)+B) - 32768 Pa"""
    if len(data) < 2:
        return 0.0
    return float(((data[0] << 8) | data[1]) - 32768)


def _decode_ac_pressure(data: bytes) -> float:
    """AC pressure: ((A*256)+B) / 100 bar"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_steering_angle(data: bytes) -> float:
    """Steering angle: ((A*256)+B) / 10 - 3276.8 degrees (signed)"""
    if len(data) < 2:
        return 0.0
    raw = (data[0] << 8) | data[1]
    return raw / 10.0 - 3276.8


def _decode_brake_pressure(data: bytes) -> float:
    """Brake pressure: ((A*256)+B) / 100 bar"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0


def _decode_yaw_rate(data: bytes) -> float:
    """Yaw rate: ((A*256)+B) / 100 - 327.68 degrees/s"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 100.0 - 327.68


def _decode_accel_g(data: bytes) -> float:
    """Acceleration: ((A*256)+B) / 1000 - 32.768 g"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 1000.0 - 32.768


def _decode_gear(data: bytes) -> str:
    """Gear engaged: number or 'R' / 'N'"""
    if not data:
        return "N"
    g = data[0]
    if g == 0:
        return "N"
    if g == 0xFF or g == 7:
        return "R"
    return str(g)


def _decode_cam_angle(data: bytes) -> float:
    """Camshaft angle: ((A*256)+B) / 10 ° CA"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 10.0


def _decode_air_mass_stroke(data: bytes) -> float:
    """Air mass per stroke: ((A*256)+B) / 10 mg"""
    if len(data) < 2:
        return 0.0
    return ((data[0] << 8) | data[1]) / 10.0


def _decode_bool_byte(data: bytes) -> int:
    """Boolean byte: 0 or 1"""
    if not data:
        return 0
    return 1 if data[0] else 0


def _decode_raw_byte(data: bytes) -> int:
    """Raw single byte value"""
    if not data:
        return 0
    return data[0]


def _decode_hex8(data: bytes) -> str:
    """Hex 8-bit"""
    if not data:
        return "0x00"
    return f"0x{data[0]:02X}"


def _decode_hex32(data: bytes) -> str:
    """Hex 32-bit"""
    if len(data) < 4:
        return "0x" + data.hex().upper()
    return f"0x{struct.unpack('>I', data[:4])[0]:08X}"


def _decode_ascii(data: bytes) -> str:
    """ASCII string (strip nulls)"""
    return data.decode("ascii", errors="replace").rstrip("\x00").strip()


# Map decoder names to functions
_DECODERS: dict[str, Callable] = {
    "rpm": _decode_rpm,
    "percent": _decode_percent,
    "percent16": _decode_percent16,
    "temp": _decode_temp,
    "temp16": _decode_temp16,
    "exhaust_temp": _decode_exhaust_temp,
    "fuel_trim": _decode_fuel_trim,
    "timing": _decode_timing,
    "maf": _decode_maf,
    "speed": _decode_speed,
    "wheel_speed": _decode_wheel_speed,
    "voltage": _decode_voltage,
    "voltage16": _decode_voltage16,
    "battery_voltage": _decode_battery_voltage,
    "pressure_kpa": _decode_pressure_kpa,
    "fuel_pressure": _decode_fuel_pressure,
    "injector_pw": _decode_injector_pw,
    "fuel_rate": _decode_fuel_rate,
    "lambda_int": _decode_lambda_int,
    "lambda_val": _decode_lambda_val,
    "o2_voltage": _decode_o2_voltage,
    "o2_current": _decode_o2_current,
    "torque": _decode_torque,
    "torque_small": _decode_torque_small,
    "knock_retard": _decode_knock_retard,
    "dwell": _decode_dwell,
    "counter16": _decode_counter16,
    "distance16": _decode_distance16,
    "runtime16": _decode_runtime16,
    "vanos_angle": _decode_vanos_angle,
    "vt_angle": _decode_vt_angle,
    "valve_lift": _decode_valve_lift,
    "current": _decode_current,
    "current16": _decode_current16,
    "angle": _decode_angle,
    "oil_pressure": _decode_oil_pressure,
    "oil_level": _decode_oil_level,
    "evap_pressure": _decode_evap_pressure,
    "ac_pressure": _decode_ac_pressure,
    "steering_angle": _decode_steering_angle,
    "brake_pressure": _decode_brake_pressure,
    "yaw_rate": _decode_yaw_rate,
    "accel_g": _decode_accel_g,
    "gear": _decode_gear,
    "cam_angle": _decode_cam_angle,
    "air_mass_stroke": _decode_air_mass_stroke,
    "bool_byte": _decode_bool_byte,
    "raw_byte": _decode_raw_byte,
    "hex8": _decode_hex8,
    "hex32": _decode_hex32,
    "ascii": _decode_ascii,
}


def decode_parameter(param: dict, raw_data: bytes):
    """Decode raw ECU bytes for a given parameter definition."""
    decoder_name = param.get("decoder", "raw_byte")
    decoder_func = _DECODERS.get(decoder_name, _decode_raw_byte)
    return decoder_func(raw_data)


# ============================================================================
# ISO-TP (ISO 15765-2) Transport Layer
# ============================================================================


class IsoTpTransport:
    """Minimal ISO-TP implementation over python-can for BMW D-CAN."""

    def __init__(self, bus, tx_id: int, rx_id: int, timeout: float = 2.0):
        self.bus = bus
        self.tx_id = tx_id
        self.rx_id = rx_id
        self.timeout = timeout

    def send(self, payload: bytes) -> None:
        """Send an ISO-TP message (single or multi-frame)."""
        if len(payload) <= 7:
            # Single frame
            frame_data = bytes([len(payload)]) + payload
            frame_data = frame_data.ljust(8, b"\x00")
            msg = can.Message(
                arbitration_id=self.tx_id, data=frame_data, is_extended_id=False
            )
            self.bus.send(msg)
        else:
            # First frame
            total_len = len(payload)
            ff_byte0 = 0x10 | ((total_len >> 8) & 0x0F)
            ff_byte1 = total_len & 0xFF
            first_data = bytes([ff_byte0, ff_byte1]) + payload[:6]
            msg = can.Message(
                arbitration_id=self.tx_id, data=first_data, is_extended_id=False
            )
            self.bus.send(msg)

            # Wait for flow control
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                rx = self.bus.recv(timeout=self.timeout)
                if rx and rx.arbitration_id == self.rx_id:
                    if rx.data[0] & 0xF0 == ISOTP_FLOW_CONTROL:
                        break

            # Consecutive frames
            offset = 6
            seq = 1
            while offset < total_len:
                cf_byte0 = 0x20 | (seq & 0x0F)
                chunk = payload[offset : offset + 7]
                frame_data = bytes([cf_byte0]) + chunk
                frame_data = frame_data.ljust(8, b"\x00")
                msg = can.Message(
                    arbitration_id=self.tx_id, data=frame_data, is_extended_id=False
                )
                self.bus.send(msg)
                offset += 7
                seq = (seq + 1) & 0x0F
                time.sleep(0.001)  # Minimum separation time

    def receive(self) -> bytes:
        """Receive an ISO-TP message (single or multi-frame reassembly)."""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            msg = self.bus.recv(timeout=self.timeout)
            if not msg or msg.arbitration_id != self.rx_id:
                continue

            frame_type = msg.data[0] & 0xF0

            if frame_type == ISOTP_SINGLE:
                length = msg.data[0] & 0x0F
                return bytes(msg.data[1 : 1 + length])

            if frame_type == ISOTP_FIRST:
                total_len = ((msg.data[0] & 0x0F) << 8) | msg.data[1]
                payload = bytearray(msg.data[2:8])

                # Send flow control
                fc = can.Message(
                    arbitration_id=self.tx_id,
                    data=bytes([0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
                    is_extended_id=False,
                )
                self.bus.send(fc)

                expected_seq = 1
                while len(payload) < total_len and time.time() < deadline:
                    rx = self.bus.recv(timeout=self.timeout)
                    if not rx or rx.arbitration_id != self.rx_id:
                        continue
                    if rx.data[0] & 0xF0 == ISOTP_CONSECUTIVE:
                        seq = rx.data[0] & 0x0F
                        if seq == expected_seq:
                            remaining = total_len - len(payload)
                            chunk_size = min(7, remaining)
                            payload.extend(rx.data[1 : 1 + chunk_size])
                            expected_seq = (expected_seq + 1) & 0x0F

                return bytes(payload[:total_len])

        raise TimeoutError("ISO-TP receive timed out")


# ============================================================================
# BMW UDS Diagnostic Client
# ============================================================================


class BMWDiagClient:
    """UDS client tailored for BMW E90 MSV70 DME (N46B20B engine)."""

    def __init__(
        self,
        interface: str = "pcan",
        channel: str = "PCAN_USBBUS1",
        port: str | None = None,
        bitrate: int = DCAN_BITRATE,
    ):
        self.interface = interface
        self.channel = channel
        self.port = port
        self.bitrate = bitrate
        self.bus = None
        self.tp = None
        self._connected = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Establish a CAN bus connection and enter extended diagnostic session."""
        if not CAN_AVAILABLE:
            logger.error(
                "python-can is not installed. Install with: pip install python-can"
            )
            return False

        try:
            kwargs = {"interface": self.interface, "bitrate": self.bitrate}

            # Interface-specific configuration
            if self.interface == "pcan":
                kwargs["channel"] = self.channel
            elif self.interface == "socketcan":
                kwargs["channel"] = self.channel or "can0"
            elif self.interface == "vector":
                kwargs["channel"] = 0
                kwargs["app_name"] = "BMW_Diag"
            elif self.interface in ("serial", "slcan"):
                if not self.port:
                    self.port = self._detect_serial_port()
                kwargs["interface"] = "slcan"
                kwargs["channel"] = self.port
            elif self.interface == "ixxat":
                kwargs["channel"] = 0
            else:
                kwargs["channel"] = self.channel

            logger.info(
                "Connecting via %s (channel=%s, bitrate=%d) ...",
                self.interface,
                kwargs.get("channel", "N/A"),
                self.bitrate,
            )
            self.bus = can.Bus(**kwargs)
            self.tp = IsoTpTransport(self.bus, DME_REQUEST_ID, DME_RESPONSE_ID)

            # Enter extended diagnostic session
            if self._enter_extended_session():
                self._connected = True
                logger.info("Connected to MSV70 DME – extended session active.")
                return True
            else:
                logger.warning(
                    "Connected to CAN bus but could not enter extended session."
                )
                return False

        except Exception as exc:
            logger.error("Connection failed: %s", exc)
            return False

    def disconnect(self) -> None:
        """Close the CAN bus connection."""
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception:
                pass
        self._connected = False
        logger.info("Disconnected.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Low-level UDS services
    # ------------------------------------------------------------------

    def _send_uds(self, service_id: int, *args: int) -> bytes | None:
        """Send a UDS request and return the positive response payload."""
        payload = bytes([service_id] + list(args))
        try:
            self.tp.send(payload)
            response = self.tp.receive()
        except TimeoutError:
            return None

        if not response:
            return None

        # Check for positive response
        if response[0] == service_id + UDS_POSITIVE_RESPONSE_OFFSET:
            return response[1:]

        # Negative response (0x7F)
        if response[0] == 0x7F and len(response) >= 3:
            nrc = response[2]
            logger.debug(
                "Negative response for SID 0x%02X: NRC=0x%02X", service_id, nrc
            )
        return None

    def _enter_extended_session(self) -> bool:
        """Request UDS extended diagnostic session."""
        resp = self._send_uds(UDS_DIAGNOSTIC_SESSION_CONTROL, SESSION_EXTENDED)
        return resp is not None

    def send_tester_present(self) -> bool:
        """Send tester-present to keep the session alive."""
        resp = self._send_uds(UDS_TESTER_PRESENT, 0x00)
        return resp is not None

    def read_did(self, did: int) -> bytes | None:
        """Read a Data Identifier (DID) via UDS ReadDataByIdentifier (0x22)."""
        high = (did >> 8) & 0xFF
        low = did & 0xFF
        resp = self._send_uds(UDS_READ_DATA_BY_IDENTIFIER, high, low)
        if resp and len(resp) >= 2:
            # Response: DID_high, DID_low, data...
            return resp[2:]
        return None

    # ------------------------------------------------------------------
    # Serial port detection (Windows)
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_serial_port() -> str:
        """Try to auto-detect a BMW K+DCAN or FTDI cable on Windows."""
        if not SERIAL_AVAILABLE:
            raise RuntimeError(
                "pyserial is not installed. Install with: pip install pyserial"
            )

        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            vid_pid = f"{p.vid:04X}:{p.pid:04X}" if p.vid and p.pid else ""
            # Common BMW K+DCAN cable identifiers
            if any(
                kw in desc
                for kw in ("ft232", "ftdi", "k+dcan", "bmw", "inpa", "usb-serial")
            ):
                logger.info("Auto-detected interface on %s (%s)", p.device, desc)
                return p.device
            if vid_pid in ("0403:6001", "0403:6015"):
                logger.info(
                    "Auto-detected FTDI cable on %s (VID:PID %s)", p.device, vid_pid
                )
                return p.device

        # Fallback
        if ports:
            logger.warning(
                "No BMW cable detected; falling back to %s", ports[0].device
            )
            return ports[0].device

        raise RuntimeError("No serial ports found. Is the diagnostic cable connected?")


# ============================================================================
# PYDABAUS – BMW Diagnostic Automation Bridge / Abstraction Utility Service
# ============================================================================


class PYDABAUS:
    """
    PYDABAUS (Python Diagnostic Automation Bridge / Abstraction Utility Service)

    High-level automation layer that wraps the BMW UDS diagnostic client to
    provide ISTA+ / EDDIBAS compatible parameter reading, batch logging,
    and interactive parameter selection for the E90 N46B20B ECU.
    """

    def __init__(self, client: BMWDiagClient):
        self.client = client
        self.catalogue = list(_PARAMETER_CATALOGUE)  # local copy
        self.selected_params: list[dict] = []
        self._tester_present_interval = 2.0  # seconds

    # ------------------------------------------------------------------
    # Parameter Catalogue helpers
    # ------------------------------------------------------------------

    def get_all_parameters(self) -> list[dict]:
        """Return the full parameter catalogue."""
        return list(self.catalogue)

    def get_categories(self) -> list[str]:
        """Return sorted list of unique parameter categories."""
        return sorted({p["category"] for p in self.catalogue})

    def get_parameters_by_category(self, category: str) -> list[dict]:
        """Return parameters belonging to a specific category."""
        return [p for p in self.catalogue if p["category"] == category]

    def select_parameters(self, indices: list[int]) -> list[dict]:
        """Select parameters by their 1-based index in the catalogue."""
        self.selected_params = []
        for idx in indices:
            if 1 <= idx <= len(self.catalogue):
                self.selected_params.append(self.catalogue[idx - 1])
        return self.selected_params

    def select_all_parameters(self) -> list[dict]:
        """Select every parameter in the catalogue for logging."""
        self.selected_params = list(self.catalogue)
        return self.selected_params

    def select_categories(self, categories: list[str]) -> list[dict]:
        """Select all parameters belonging to the given categories."""
        cats_lower = {c.lower() for c in categories}
        self.selected_params = [
            p for p in self.catalogue if p["category"].lower() in cats_lower
        ]
        return self.selected_params

    # ------------------------------------------------------------------
    # Single parameter read
    # ------------------------------------------------------------------

    def read_parameter(self, param: dict) -> tuple:
        """Read a single parameter from the ECU.

        Returns:
            (name, decoded_value, unit, raw_hex)
        """
        raw = self.client.read_did(param["did"])
        if raw is None:
            return (param["name"], None, param["unit"], "N/A")
        decoded = decode_parameter(param, raw)
        raw_hex = raw.hex().upper()
        return (param["name"], decoded, param["unit"], raw_hex)

    # ------------------------------------------------------------------
    # Batch read
    # ------------------------------------------------------------------

    def read_all_selected(self) -> list[tuple]:
        """Read all selected parameters in one sweep.

        Returns list of (name, value, unit, raw_hex).
        """
        results = []
        for param in self.selected_params:
            results.append(self.read_parameter(param))
        return results

    # ------------------------------------------------------------------
    # Continuous logging
    # ------------------------------------------------------------------

    def log_to_csv(
        self,
        filepath: str,
        interval_ms: int = 100,
        duration_s: float = 0,
        callback=None,
    ) -> None:
        """Continuously log selected parameters to a CSV file.

        Args:
            filepath:    Output CSV path.
            interval_ms: Milliseconds between read sweeps.
            duration_s:  Total logging duration in seconds (0 = until Ctrl+C).
            callback:    Optional callable(row_dict) invoked per sweep.
        """
        if not self.selected_params:
            logger.warning("No parameters selected for logging.")
            return

        fieldnames = ["Timestamp"] + [p["name"] for p in self.selected_params]

        # Ensure output directory exists
        out_dir = os.path.dirname(filepath) or "."
        os.makedirs(out_dir, exist_ok=True)

        logger.info(
            "Logging %d parameters to %s (interval=%d ms, duration=%s) ...",
            len(self.selected_params),
            filepath,
            interval_ms,
            f"{duration_s}s" if duration_s else "unlimited",
        )
        logger.info("Press Ctrl+C to stop logging.\n")

        start_time = time.time()
        last_tp = start_time
        sweep_count = 0

        with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            try:
                while True:
                    sweep_start = time.time()

                    # Tester-present keep-alive
                    if sweep_start - last_tp >= self._tester_present_interval:
                        self.client.send_tester_present()
                        last_tp = sweep_start

                    # Read all parameters
                    row = {
                        "Timestamp": datetime.datetime.now().isoformat(
                            timespec="milliseconds"
                        )
                    }
                    for param in self.selected_params:
                        _name, value, _unit, _raw = self.read_parameter(param)
                        row[param["name"]] = value

                    writer.writerow(row)
                    csvfile.flush()
                    sweep_count += 1

                    if callback:
                        callback(row)

                    # Check duration limit
                    elapsed = time.time() - start_time
                    if duration_s and elapsed >= duration_s:
                        break

                    # Maintain requested interval
                    sweep_elapsed = time.time() - sweep_start
                    sleep_time = (interval_ms / 1000.0) - sweep_elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            except KeyboardInterrupt:
                pass

        total_elapsed = time.time() - start_time
        logger.info(
            "Logging complete: %d sweeps in %.1f s → %s",
            sweep_count,
            total_elapsed,
            filepath,
        )


# ============================================================================
# Interactive CLI
# ============================================================================

BANNER = r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║             BMW E90 320i N46B20B – ECU Diagnostics & Data Logger           ║
║                                                                            ║
║  Engine:    N46B20B (2.0 L 4-cyl, Valvetronic)                            ║
║  ECU:       Siemens MSV70                                                  ║
║  Protocol:  UDS over D-CAN (500 kbps)                                     ║
║  Tools:     ISTA+ / EDDIBAS / PYDABAUS                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

SEPARATOR = "─" * 78


def print_banner() -> None:
    """Print the application banner."""
    print(BANNER)


def print_parameter_catalogue() -> None:
    """Print the full parameter catalogue in a formatted table."""
    print(f"\n{SEPARATOR}")
    print(
        f"  COMPLETE ECU PARAMETER CATALOGUE  –  {TOTAL_PARAMETER_COUNT} parameters"
    )
    print(SEPARATOR)

    current_category = ""
    for idx, param in enumerate(_PARAMETER_CATALOGUE, 1):
        if param["category"] != current_category:
            current_category = param["category"]
            print(f"\n  ┌─ {current_category} {'─' * (70 - len(current_category))}")

        did_str = f"0x{param['did']:04X}"
        unit_str = f"[{param['unit']}]" if param["unit"] else ""
        print(
            f"  │ {idx:>3}. {did_str}  {param['name']:<45s} {unit_str:<10s}"
        )
        print(f"  │       └─ {param['description']}")

    print(f"\n{SEPARATOR}")
    print(f"  Total available parameters: {TOTAL_PARAMETER_COUNT}")
    print(SEPARATOR)


def interactive_parameter_selection(pydabaus_inst: PYDABAUS) -> list[dict]:
    """Prompt the user to select which parameters to log.

    Returns the list of selected parameter dicts.
    """
    print(f"\n{SEPARATOR}")
    print("  PARAMETER SELECTION")
    print(SEPARATOR)
    print()
    print("  Choose how to select parameters:\n")
    print("    [A] Log ALL parameters (full ECU data dump)")
    print("    [C] Select by category")
    print("    [S] Select individual parameters by number")
    print("    [Q] Quit / Cancel")
    print()

    while True:
        choice = input("  Enter choice (A/C/S/Q): ").strip().upper()

        if choice == "A":
            selected = pydabaus_inst.select_all_parameters()
            print(
                f"\n  ✓ Selected ALL {len(selected)} parameters for logging."
            )
            return selected

        elif choice == "C":
            categories = pydabaus_inst.get_categories()
            print("\n  Available categories:\n")
            for i, cat in enumerate(categories, 1):
                count = len(pydabaus_inst.get_parameters_by_category(cat))
                print(f"    {i:>2}. {cat} ({count} params)")
            print(f"    {'':>2}  [Enter numbers separated by commas, or 'all']")
            print()

            cat_input = input("  Select categories: ").strip()
            if cat_input.lower() == "all":
                selected = pydabaus_inst.select_all_parameters()
            else:
                try:
                    cat_indices = [
                        int(x.strip()) for x in cat_input.split(",") if x.strip()
                    ]
                    chosen_cats = [
                        categories[i - 1]
                        for i in cat_indices
                        if 1 <= i <= len(categories)
                    ]
                    selected = pydabaus_inst.select_categories(chosen_cats)
                except (ValueError, IndexError):
                    print("  ✗ Invalid input. Try again.")
                    continue

            print(f"\n  ✓ Selected {len(selected)} parameters from chosen categories.")
            return selected

        elif choice == "S":
            print(
                "\n  Enter parameter numbers separated by commas, "
                "or ranges like 1-10,15,20-30:"
            )
            sel_input = input("  Parameters: ").strip()
            indices = _parse_number_list(sel_input)
            if not indices:
                print("  ✗ No valid numbers entered. Try again.")
                continue
            selected = pydabaus_inst.select_parameters(indices)
            print(f"\n  ✓ Selected {len(selected)} parameters for logging.")
            return selected

        elif choice == "Q":
            return []

        else:
            print("  ✗ Invalid choice. Please enter A, C, S, or Q.")


def _parse_number_list(text: str) -> list[int]:
    """Parse a string like '1-5,8,10-12' into a sorted list of integers."""
    result: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                result.extend(range(int(start.strip()), int(end.strip()) + 1))
            except ValueError:
                continue
        else:
            try:
                result.append(int(part))
            except ValueError:
                continue
    return sorted(set(result))


def configure_connection(args) -> BMWDiagClient:
    """Create and return a BMWDiagClient based on CLI arguments."""
    # Map user-friendly interface names
    iface_map = {
        "pcan": "pcan",
        "kvaser": "kvaser",
        "vector": "vector",
        "ixxat": "ixxat",
        "socketcan": "socketcan",
        "slcan": "slcan",
        "serial": "slcan",
        "kdcan": "slcan",
        "usb": "slcan",
    }
    interface = iface_map.get(args.interface.lower(), args.interface)

    return BMWDiagClient(
        interface=interface,
        channel=args.channel,
        port=args.port,
        bitrate=args.bitrate,
    )


def live_display_callback(row: dict) -> None:
    """Print a condensed live view of key parameters to the console."""
    ts = row.get("Timestamp", "")
    rpm = row.get("Engine_RPM", "---")
    coolant = row.get("Coolant_Temperature", "---")
    speed = row.get("Vehicle_Speed", "---")
    load = row.get("Engine_Load", "---")
    throttle = row.get("Throttle_Position", "---")

    if isinstance(rpm, float):
        rpm = f"{rpm:.0f}"
    if isinstance(coolant, float):
        coolant = f"{coolant:.1f}"
    if isinstance(speed, float):
        speed = f"{speed:.0f}"
    if isinstance(load, float):
        load = f"{load:.1f}"
    if isinstance(throttle, float):
        throttle = f"{throttle:.1f}"

    line = (
        f"  {ts}  RPM={rpm:>6s}  "
        f"Coolant={coolant:>6s}°C  "
        f"Speed={speed:>4s} km/h  "
        f"Load={load:>5s}%  "
        f"Throttle={throttle:>5s}%"
    )
    print(f"\r{line}", end="", flush=True)


# ============================================================================
# Offline / Demo mode for testing without hardware
# ============================================================================


class OfflineDemoClient:
    """Simulated ECU client that returns plausible fake data for testing."""

    def __init__(self):
        self._connected = True
        import random

        self._random = random

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        logger.info("[DEMO] Simulated connection to MSV70 DME.")
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("[DEMO] Disconnected.")

    def send_tester_present(self) -> bool:
        return True

    def read_did(self, did: int) -> bytes:
        """Generate plausible random bytes for demonstration."""
        r = self._random
        # Return 2-4 bytes of random data
        length = r.choice([1, 2, 2, 2, 4])
        return bytes(r.randint(0, 255) for _ in range(length))


# ============================================================================
# Sensor Availability Testing
# ============================================================================


def test_sensor_availability(
    pydabaus_inst: "PYDABAUS",
    progress_callback: Callable | None = None,
) -> dict[str, dict]:
    """Probe every parameter in the catalogue and report which sensors respond.

    For each sensor that does **not** respond the function logs an ERROR so
    operators can review missing hardware / ECU support.

    Args:
        pydabaus_inst:     An initialised PYDABAUS instance with an active client.
        progress_callback: Optional callable(current: int, total: int, name: str)
                           that is invoked after each sensor is tested – useful for
                           updating a progress bar in a GUI or CLI.

    Returns:
        A dict mapping each parameter name to::

            {
                "available": bool,   # True if the ECU returned data
                "error":     str|None,  # Error description when unavailable
            }

    Example::

        client = OfflineDemoClient()
        client.connect()
        pydabaus = PYDABAUS(client)
        results = test_sensor_availability(pydabaus)
        missing = {k: v for k, v in results.items() if not v["available"]}
    """
    catalogue = pydabaus_inst.get_all_parameters()
    total = len(catalogue)
    results: dict[str, dict] = {}

    for idx, param in enumerate(catalogue):
        name = param["name"]
        did = param["did"]

        if progress_callback is not None:
            progress_callback(idx + 1, total, name)

        try:
            raw = pydabaus_inst.client.read_did(did)
        except Exception as exc:  # noqa: BLE001
            raw = None
            error_msg = str(exc)
        else:
            error_msg = None if raw is not None else f"No response for DID 0x{did:04X}"

        available = raw is not None
        results[name] = {"available": available, "error": error_msg}

        if not available:
            logger.error(
                "SENSOR UNAVAILABLE: %s (DID 0x%04X) – %s",
                name,
                did,
                error_msg or "no data",
            )

    available_count = sum(1 for v in results.values() if v["available"])
    missing_count = total - available_count
    logger.info(
        "Sensor availability test complete: %d/%d available, %d missing.",
        available_count,
        total,
        missing_count,
    )
    if missing_count:
        logger.error(
            "%d sensor(s) did not respond. Review the log for SENSOR UNAVAILABLE entries.",
            missing_count,
        )

    return results


# ============================================================================
# Entry Point
# ============================================================================


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="BMW E90 320i N46B20B – ECU Diagnostics & Data Logger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s --interface pcan
              %(prog)s --interface slcan --port COM3
              %(prog)s --interface kdcan --port COM5 --log-all --rate 200
              %(prog)s --demo --log-all --duration 10 --output demo_log.csv
              %(prog)s --list-params
        """),
    )

    conn_group = parser.add_argument_group("Connection")
    conn_group.add_argument(
        "--interface",
        "-i",
        default="pcan",
        help="CAN interface type: pcan, kvaser, vector, ixxat, slcan, kdcan, "
        "socketcan (default: pcan)",
    )
    conn_group.add_argument(
        "--channel",
        "-c",
        default="PCAN_USBBUS1",
        help="CAN channel (default: PCAN_USBBUS1)",
    )
    conn_group.add_argument(
        "--port",
        "-p",
        default=None,
        help="Serial port for K+DCAN cable (e.g. COM3). Auto-detected if omitted.",
    )
    conn_group.add_argument(
        "--bitrate",
        "-b",
        type=int,
        default=DCAN_BITRATE,
        help=f"CAN bus bitrate (default: {DCAN_BITRATE})",
    )

    log_group = parser.add_argument_group("Logging")
    log_group.add_argument(
        "--log-all",
        action="store_true",
        help="Log all available parameters without prompting",
    )
    log_group.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output CSV file path (default: bmw_log_<timestamp>.csv)",
    )
    log_group.add_argument(
        "--rate",
        "-r",
        type=int,
        default=100,
        help="Logging interval in milliseconds (default: 100)",
    )
    log_group.add_argument(
        "--duration",
        "-d",
        type=float,
        default=0,
        help="Logging duration in seconds (default: 0 = unlimited)",
    )

    misc_group = parser.add_argument_group("Miscellaneous")
    misc_group.add_argument(
        "--list-params",
        action="store_true",
        help="Print all available parameters and exit",
    )
    misc_group.add_argument(
        "--demo",
        action="store_true",
        help="Run in offline demo mode with simulated ECU data",
    )
    misc_group.add_argument(
        "--test-sensors",
        action="store_true",
        help="Test which sensors are available and log any that are missing",
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = build_argument_parser()
    args = parser.parse_args()

    print_banner()

    # ── List parameters only ──────────────────────────────────────────
    if args.list_params:
        print_parameter_catalogue()
        return 0

    # ── Create client ─────────────────────────────────────────────────
    if args.demo:
        logger.info("Running in DEMO mode (no hardware required).")
        client = OfflineDemoClient()
    else:
        client = configure_connection(args)

    # ── Connect to ECU ────────────────────────────────────────────────
    if not client.connect():
        logger.error(
            "Failed to connect to the ECU. Check cable, ignition, and interface settings."
        )
        return 1

    # ── PYDABAUS automation layer ─────────────────────────────────────
    pydabaus = PYDABAUS(client)

    # ── Sensor availability test ──────────────────────────────────────
    if args.test_sensors:
        print(f"\n{SEPARATOR}")
        print("  SENSOR AVAILABILITY TEST")
        print(SEPARATOR)

        def _progress(current, total, name):
            pct = int(current * 100 / total)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {current}/{total}  {name:<50s}", end="", flush=True)

        results = test_sensor_availability(pydabaus, progress_callback=_progress)
        print()  # newline after progress line

        available = {k for k, v in results.items() if v["available"]}
        missing = {k: v["error"] for k, v in results.items() if not v["available"]}

        print(f"\n  Total parameters : {len(results)}")
        print(f"  Available        : {len(available)}")
        print(f"  Missing / errors : {len(missing)}")

        if missing:
            print(f"\n{SEPARATOR}")
            print("  MISSING / UNAVAILABLE SENSORS (logged as errors):")
            print(SEPARATOR)
            for name, err in sorted(missing.items()):
                print(f"  ✗  {name:<50s}  {err or ''}")
        else:
            print("\n  ✓ All sensors responded successfully.")

        print(f"\n{SEPARATOR}")
        client.disconnect()
        return 0 if not missing else 2

    # ── Show parameter catalogue ──────────────────────────────────────
    print_parameter_catalogue()

    # ── Select parameters ─────────────────────────────────────────────
    if args.log_all:
        selected = pydabaus.select_all_parameters()
        print(
            f"\n  ✓ Auto-selected ALL {len(selected)} parameters (--log-all)."
        )
    else:
        selected = interactive_parameter_selection(pydabaus)
        if not selected:
            logger.info("No parameters selected. Exiting.")
            client.disconnect()
            return 0

    # ── Prepare output file ───────────────────────────────────────────
    if args.output:
        output_path = args.output
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"bmw_log_{ts}.csv"

    # ── Begin logging ─────────────────────────────────────────────────
    print(f"\n{SEPARATOR}")
    print(f"  LOGGING: {len(selected)} parameters → {output_path}")
    print(f"  Rate: {args.rate} ms | Duration: ", end="")
    print(f"{args.duration} s" if args.duration else "unlimited (Ctrl+C to stop)")
    print(SEPARATOR)

    try:
        pydabaus.log_to_csv(
            filepath=output_path,
            interval_ms=args.rate,
            duration_s=args.duration,
            callback=live_display_callback,
        )
    finally:
        print()  # newline after \r live display
        client.disconnect()

    print(f"\n  Log saved to: {os.path.abspath(output_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
