#!/usr/bin/env python3
"""
BMW E90 320i N46B20B – ECU Diagnostics GUI Dashboard
======================================================

A tkinter-based graphical interface providing an ISTA-style dashboard for
real-time sensor monitoring and data recording via FTDI K+DCAN cables.

Features:
  - Sensor selection by category or individual parameter
  - Live dashboard with continuously updated values
  - CSV data recording with start/stop controls
  - Sensor availability test that logs missing parameters as errors
  - Demo mode (no hardware required)

Usage:
    python bmw_e90_gui.py [--demo] [--port COM3] [--interface kdcan]

Author:  BMW Diagnostics Project
License: MIT
"""

import argparse
import datetime
import logging
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

# Ensure the repo root is on the path so we can import the core module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmw_e90_diagnostics as diag

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("bmw_gui")

# ---------------------------------------------------------------------------
# Colour palette – dark theme similar to ISTA/ISTA+
# ---------------------------------------------------------------------------
C_BG = "#1a1a2e"          # Main background
C_PANEL = "#16213e"       # Panel background
C_ACCENT = "#0f3460"      # Accent / header bars
C_HIGHLIGHT = "#e94560"   # Active / alert colour
C_TEXT = "#eaeaea"        # Normal text
C_TEXT_DIM = "#8a8a9a"    # Dim / label text
C_GREEN = "#00d2a0"       # Good / connected
C_YELLOW = "#f5c518"      # Warning
C_RED = "#e94560"         # Error / disconnected
C_BLUE = "#4ecca3"        # Value display colour
C_SEL = "#0f3460"         # Checkbox selection highlight
C_HEADER = "#e94560"      # Header text
C_BTN = "#0f3460"         # Button background
C_BTN_ACTIVE = "#1a4a80"  # Button hover

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
REFRESH_MS = 250          # Dashboard refresh interval (ms)
FONT_FAMILY = "Courier New"
FONT_SIZE_TITLE = 14
FONT_SIZE_HEADER = 11
FONT_SIZE_NORMAL = 10
FONT_SIZE_VALUE = 12
FONT_SIZE_SMALL = 9


class SensorAvailabilityTester:
    """Tests which ECU sensors respond and logs unavailable ones as errors."""

    def __init__(self, pydabaus_inst: diag.PYDABAUS):
        self.pydabaus = pydabaus_inst
        self.results: dict[str, dict] = {}  # name -> {available, error}

    def run(
        self,
        progress_callback=None,
        done_callback=None,
    ) -> dict[str, dict]:
        """
        Probe every sensor in the parameter catalogue.

        For each sensor that fails to respond, logs an ERROR so operators can
        review missing hardware / ECU support.

        Args:
            progress_callback: callable(current, total, param_name) for UI updates.
            done_callback:     callable(results) invoked when finished.

        Returns:
            dict mapping parameter name to {'available': bool, 'error': str|None}.
        """
        catalogue = self.pydabaus.get_all_parameters()
        total = len(catalogue)
        self.results = {}

        for idx, param in enumerate(catalogue):
            name = param["name"]
            if progress_callback:
                progress_callback(idx + 1, total, name)

            try:
                raw = self.pydabaus.client.read_did(param["did"])
                if raw is None:
                    self.results[name] = {
                        "available": False,
                        "error": f"No response for DID 0x{param['did']:04X}",
                    }
                    logger.error(
                        "SENSOR UNAVAILABLE: %s (DID 0x%04X) – no ECU response",
                        name,
                        param["did"],
                    )
                else:
                    self.results[name] = {"available": True, "error": None}
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                self.results[name] = {"available": False, "error": str(exc)}
                logger.error(
                    "SENSOR ERROR: %s (DID 0x%04X) – %s",
                    name,
                    param["did"],
                    exc,
                )

        available = sum(1 for v in self.results.values() if v["available"])
        missing = total - available
        logger.info(
            "Sensor availability test complete: %d/%d available, %d missing.",
            available,
            total,
            missing,
        )
        if missing:
            logger.error(
                "%d sensor(s) did not respond. Review log for SENSOR UNAVAILABLE entries.",
                missing,
            )

        if done_callback:
            done_callback(self.results)

        return self.results

    def run_in_thread(self, progress_callback=None, done_callback=None) -> threading.Thread:
        """Run the availability test in a background thread."""
        t = threading.Thread(
            target=self.run,
            kwargs={"progress_callback": progress_callback, "done_callback": done_callback},
            daemon=True,
        )
        t.start()
        return t


# ============================================================================
# Main GUI Application
# ============================================================================


class BmwDiagGUI:
    """
    ISTA-style graphical diagnostic dashboard for BMW E90 N46B20B.

    Layout:
    ┌──────────────── title bar ─────────────────┐
    │ ┌── left panel ──┐  ┌─── dashboard ──────┐ │
    │ │ sensor list    │  │ live value tiles    │ │
    │ │ + checkboxes   │  │                     │ │
    │ │                │  │                     │ │
    │ └────────────────┘  └─────────────────────┘ │
    │ ┌── status bar ──────────────────────────┐  │
    │ └────────────────────────────────────────┘  │
    └─────────────────────────────────────────────┘
    """

    def __init__(self, root: tk.Tk, args):
        self.root = root
        self.args = args
        self.client = None
        self.pydabaus = None
        self.tester = None
        self._logging_active = False
        self._log_thread = None
        self._log_filepath = None
        self._lock = threading.Lock()
        self._latest_row: dict = {}
        self._sensor_vars: dict[str, tk.BooleanVar] = {}
        self._value_labels: dict[str, tk.Label] = {}
        self._tile_frames: dict[str, tk.Frame] = {}

        self._build_ui()
        self._connect()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.root.title("BMW E90 N46B20B – ECU Diagnostics Dashboard")
        self.root.configure(bg=C_BG)
        self.root.geometry("1400x860")
        self.root.minsize(900, 600)

        # ── Title bar ──────────────────────────────────────────────────
        self._build_title_bar()

        # ── Main content area ──────────────────────────────────────────
        content = tk.Frame(self.root, bg=C_BG)
        content.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        # Left panel – sensor selection
        left = tk.Frame(content, bg=C_PANEL, width=320, relief=tk.FLAT, bd=0)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left.pack_propagate(False)
        self._build_left_panel(left)

        # Right – dashboard tiles
        right = tk.Frame(content, bg=C_BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_dashboard(right)

        # ── Status / log bar ───────────────────────────────────────────
        self._build_status_bar()

    def _build_title_bar(self):
        bar = tk.Frame(self.root, bg=C_ACCENT, height=52)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        tk.Label(
            bar,
            text="BMW E90 320i  |  N46B20B Engine  |  MSV70 ECU  |  ECU Diagnostics Dashboard",
            bg=C_ACCENT,
            fg=C_TEXT,
            font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT, padx=14, pady=10)

        # Connection status badge
        self._conn_badge = tk.Label(
            bar,
            text=" ● DISCONNECTED ",
            bg=C_RED,
            fg="white",
            font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
        )
        self._conn_badge.pack(side=tk.RIGHT, padx=14, pady=14)

    def _build_left_panel(self, parent):
        # Header
        hdr = tk.Frame(parent, bg=C_ACCENT, height=32)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="SENSOR SELECTION",
            bg=C_ACCENT,
            fg=C_HEADER,
            font=(FONT_FAMILY, FONT_SIZE_HEADER, "bold"),
        ).pack(side=tk.LEFT, padx=10, pady=6)

        # Select-all / none buttons
        btn_row = tk.Frame(parent, bg=C_PANEL)
        btn_row.pack(fill=tk.X, padx=6, pady=4)
        for label, cmd in [
            ("All", self._select_all),
            ("None", self._select_none),
            ("Test Sensors", self._run_sensor_test_dialog),
        ]:
            tk.Button(
                btn_row,
                text=label,
                command=cmd,
                bg=C_BTN,
                fg=C_TEXT,
                relief=tk.FLAT,
                font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                padx=6,
                pady=3,
                cursor="hand2",
                activebackground=C_BTN_ACTIVE,
                activeforeground=C_TEXT,
            ).pack(side=tk.LEFT, padx=2)

        # Filter box
        filter_row = tk.Frame(parent, bg=C_PANEL)
        filter_row.pack(fill=tk.X, padx=6, pady=(0, 4))
        tk.Label(
            filter_row, text="Filter:", bg=C_PANEL, fg=C_TEXT_DIM,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
        ).pack(side=tk.LEFT)
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._apply_filter)
        filter_entry = tk.Entry(
            filter_row,
            textvariable=self._filter_var,
            bg=C_ACCENT,
            fg=C_TEXT,
            insertbackground=C_TEXT,
            relief=tk.FLAT,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
        )
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # Scrollable sensor list
        container = tk.Frame(parent, bg=C_PANEL)
        container.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        self._list_canvas = tk.Canvas(container, bg=C_PANEL, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient=tk.VERTICAL, command=self._list_canvas.yview)
        self._list_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._sensor_list_frame = tk.Frame(self._list_canvas, bg=C_PANEL)
        self._list_canvas_window = self._list_canvas.create_window(
            (0, 0), window=self._sensor_list_frame, anchor="nw"
        )

        self._sensor_list_frame.bind(
            "<Configure>",
            lambda e: self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")
            ),
        )
        self._list_canvas.bind(
            "<Configure>",
            lambda e: self._list_canvas.itemconfig(
                self._list_canvas_window, width=e.width
            ),
        )
        self._list_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._list_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

        # Populate sensor checkboxes
        self._populate_sensor_list()

        # ── Control buttons ────────────────────────────────────────────
        ctrl = tk.Frame(parent, bg=C_PANEL)
        ctrl.pack(fill=tk.X, padx=6, pady=6)

        self._start_btn = tk.Button(
            ctrl,
            text="▶  Start Recording",
            command=self._start_recording,
            bg=C_GREEN,
            fg="#000000",
            relief=tk.FLAT,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
            padx=8,
            pady=5,
            cursor="hand2",
            activebackground="#00b090",
        )
        self._start_btn.pack(fill=tk.X, pady=(0, 3))

        self._stop_btn = tk.Button(
            ctrl,
            text="■  Stop Recording",
            command=self._stop_recording,
            bg=C_RED,
            fg="white",
            relief=tk.FLAT,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
            padx=8,
            pady=5,
            cursor="hand2",
            state=tk.DISABLED,
            activebackground="#c0304a",
        )
        self._stop_btn.pack(fill=tk.X)

    def _populate_sensor_list(self, filter_text: str = ""):
        """Rebuild the sensor checkbox list, optionally filtered."""
        for widget in self._sensor_list_frame.winfo_children():
            widget.destroy()

        ft_lower = filter_text.lower()
        current_cat = None

        for param in diag._PARAMETER_CATALOGUE:
            name = param["name"]
            cat = param["category"]
            desc = param["description"]

            # Filter
            if ft_lower and ft_lower not in name.lower() and ft_lower not in cat.lower():
                continue

            # Category header
            if cat != current_cat:
                current_cat = cat
                cat_lbl = tk.Label(
                    self._sensor_list_frame,
                    text=f"  {cat}",
                    bg=C_ACCENT,
                    fg=C_HEADER,
                    font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                    anchor="w",
                )
                cat_lbl.pack(fill=tk.X, pady=(4, 0))

            # Preserve existing BooleanVar or create a new one
            if name not in self._sensor_vars:
                self._sensor_vars[name] = tk.BooleanVar(value=True)

            row = tk.Frame(self._sensor_list_frame, bg=C_PANEL)
            row.pack(fill=tk.X)

            cb = tk.Checkbutton(
                row,
                variable=self._sensor_vars[name],
                bg=C_PANEL,
                fg=C_TEXT,
                selectcolor=C_SEL,
                activebackground=C_PANEL,
                relief=tk.FLAT,
                command=self._on_selection_change,
            )
            cb.pack(side=tk.LEFT)

            lbl = tk.Label(
                row,
                text=f"{name}",
                bg=C_PANEL,
                fg=C_TEXT,
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                anchor="w",
            )
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            lbl.bind("<Button-1>", lambda e, n=name: self._toggle_sensor(n))

            unit_str = f"[{param['unit']}]" if param["unit"] else ""
            tk.Label(
                row,
                text=unit_str,
                bg=C_PANEL,
                fg=C_TEXT_DIM,
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                width=8,
                anchor="e",
            ).pack(side=tk.RIGHT, padx=4)

    def _build_dashboard(self, parent):
        # Header row
        hdr = tk.Frame(parent, bg=C_ACCENT, height=32)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="LIVE SENSOR DASHBOARD",
            bg=C_ACCENT,
            fg=C_HEADER,
            font=(FONT_FAMILY, FONT_SIZE_HEADER, "bold"),
        ).pack(side=tk.LEFT, padx=10, pady=6)

        self._rec_badge = tk.Label(
            hdr,
            text="",
            bg=C_ACCENT,
            fg=C_GREEN,
            font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
        )
        self._rec_badge.pack(side=tk.RIGHT, padx=10)

        # Scrollable tile grid
        outer = tk.Frame(parent, bg=C_BG)
        outer.pack(fill=tk.BOTH, expand=True)

        self._dash_canvas = tk.Canvas(outer, bg=C_BG, highlightthickness=0)
        vsb = tk.Scrollbar(outer, orient=tk.VERTICAL, command=self._dash_canvas.yview)
        self._dash_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._dash_canvas.pack(fill=tk.BOTH, expand=True)

        self._dash_frame = tk.Frame(self._dash_canvas, bg=C_BG)
        self._dash_canvas_window = self._dash_canvas.create_window(
            (0, 0), window=self._dash_frame, anchor="nw"
        )
        self._dash_frame.bind(
            "<Configure>",
            lambda e: self._dash_canvas.configure(
                scrollregion=self._dash_canvas.bbox("all")
            ),
        )
        self._dash_canvas.bind(
            "<Configure>",
            lambda e: self._dash_canvas.itemconfig(
                self._dash_canvas_window, width=e.width
            ),
        )

        self._rebuild_dashboard_tiles()

    def _rebuild_dashboard_tiles(self):
        """Create/recreate value tiles for currently selected sensors."""
        for widget in self._dash_frame.winfo_children():
            widget.destroy()
        self._value_labels.clear()
        self._tile_frames.clear()

        selected = self._get_selected_params()
        if not selected:
            tk.Label(
                self._dash_frame,
                text="No sensors selected.\nUse the panel on the left to choose sensors.",
                bg=C_BG,
                fg=C_TEXT_DIM,
                font=(FONT_FAMILY, FONT_SIZE_NORMAL),
                justify=tk.CENTER,
            ).pack(expand=True, pady=40)
            return

        # Tile grid – 4 columns
        cols = 4
        for i, param in enumerate(selected):
            row = i // cols
            col = i % cols

            name = param["name"]
            unit = param["unit"]
            cat = param["category"]

            tile = tk.Frame(
                self._dash_frame,
                bg=C_PANEL,
                relief=tk.FLAT,
                padx=4,
                pady=4,
                bd=1,
            )
            tile.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            self._dash_frame.grid_columnconfigure(col, weight=1)
            self._tile_frames[name] = tile

            # Category label (small, top)
            tk.Label(
                tile,
                text=cat,
                bg=C_PANEL,
                fg=C_TEXT_DIM,
                font=(FONT_FAMILY, FONT_SIZE_SMALL - 1),
                anchor="w",
            ).pack(fill=tk.X)

            # Sensor name
            tk.Label(
                tile,
                text=name.replace("_", " "),
                bg=C_PANEL,
                fg=C_TEXT,
                font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                anchor="w",
                wraplength=200,
            ).pack(fill=tk.X)

            # Value display
            val_lbl = tk.Label(
                tile,
                text="---",
                bg=C_PANEL,
                fg=C_BLUE,
                font=(FONT_FAMILY, FONT_SIZE_VALUE, "bold"),
                anchor="center",
            )
            val_lbl.pack(fill=tk.X, pady=(4, 0))
            self._value_labels[name] = val_lbl

            # Unit label
            tk.Label(
                tile,
                text=unit,
                bg=C_PANEL,
                fg=C_TEXT_DIM,
                font=(FONT_FAMILY, FONT_SIZE_SMALL),
                anchor="center",
            ).pack(fill=tk.X)

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=C_ACCENT, height=28)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self._status_var = tk.StringVar(value="Initialising…")
        tk.Label(
            bar,
            textvariable=self._status_var,
            bg=C_ACCENT,
            fg=C_TEXT,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            anchor="w",
        ).pack(side=tk.LEFT, padx=10)

        # Recording info
        self._rec_info_var = tk.StringVar(value="")
        tk.Label(
            bar,
            textvariable=self._rec_info_var,
            bg=C_ACCENT,
            fg=C_GREEN,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            anchor="e",
        ).pack(side=tk.RIGHT, padx=10)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self):
        """Connect to ECU (or start demo mode) in a background thread."""
        self._set_status("Connecting…")
        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        try:
            if self.args.demo:
                self.client = diag.OfflineDemoClient()
                self.client.connect()
            else:
                iface_map = {
                    "pcan": "pcan", "kvaser": "kvaser", "vector": "vector",
                    "ixxat": "ixxat", "socketcan": "socketcan",
                    "slcan": "slcan", "serial": "slcan", "kdcan": "slcan",
                }
                iface = iface_map.get(self.args.interface.lower(), self.args.interface)
                self.client = diag.BMWDiagClient(
                    interface=iface,
                    channel=self.args.channel,
                    port=self.args.port,
                    bitrate=self.args.bitrate,
                )
                self.client.connect()

            self.pydabaus = diag.PYDABAUS(self.client)
            self.tester = SensorAvailabilityTester(self.pydabaus)

            connected = self.client.is_connected
            self.root.after(0, self._on_connected, connected)
        except (OSError, RuntimeError, TimeoutError, ImportError, AttributeError) as exc:
            self.root.after(0, self._on_connected, False, str(exc))

    def _on_connected(self, success: bool, error: str = ""):
        if success:
            label = "DEMO MODE" if self.args.demo else "CONNECTED"
            self._conn_badge.config(text=f" ● {label} ", bg=C_GREEN, fg="#000000")
            self._set_status(
                f"Connected to MSV70 ECU | {diag.TOTAL_PARAMETER_COUNT} parameters available"
            )
        else:
            self._conn_badge.config(text=" ● DISCONNECTED ", bg=C_RED, fg="white")
            self._set_status(f"Connection failed: {error or 'Check cable and ignition'}")
            messagebox.showerror(
                "Connection Failed",
                f"Could not connect to the ECU.\n\n{error or 'Check cable, ignition, and interface settings.'}\n\nTip: use --demo flag for offline mode.",
            )
            return

        # Start live refresh loop
        self.root.after(REFRESH_MS, self._refresh_dashboard)

    # ------------------------------------------------------------------
    # Sensor selection helpers
    # ------------------------------------------------------------------

    def _get_selected_params(self) -> list[dict]:
        """Return parameter dicts for all ticked checkboxes."""
        return [
            p for p in diag._PARAMETER_CATALOGUE
            if self._sensor_vars.get(p["name"], tk.BooleanVar(value=False)).get()
        ]

    def _select_all(self):
        for var in self._sensor_vars.values():
            var.set(True)
        self._on_selection_change()

    def _select_none(self):
        for var in self._sensor_vars.values():
            var.set(False)
        self._on_selection_change()

    def _toggle_sensor(self, name: str):
        if name in self._sensor_vars:
            self._sensor_vars[name].set(not self._sensor_vars[name].get())
        self._on_selection_change()

    def _on_selection_change(self):
        self._rebuild_dashboard_tiles()

    def _apply_filter(self, *_):
        try:
            ft = self._filter_var.get()
        except tk.TclError:
            ft = ""
        self._populate_sensor_list(ft)

    # ------------------------------------------------------------------
    # Live dashboard refresh
    # ------------------------------------------------------------------

    def _refresh_dashboard(self):
        """Read selected sensors and update displayed values."""
        if not self.pydabaus:
            self.root.after(REFRESH_MS, self._refresh_dashboard)
            return

        selected = self._get_selected_params()
        if not selected:
            self.root.after(REFRESH_MS, self._refresh_dashboard)
            return

        def _read():
            row = {
                "Timestamp": datetime.datetime.now().isoformat(timespec="milliseconds")
            }
            for param in selected:
                _, value, _, _ = self.pydabaus.read_parameter(param)
                row[param["name"]] = value
            with self._lock:
                self._latest_row = row

        threading.Thread(target=_read, daemon=True).start()
        self._update_tiles()
        self.root.after(REFRESH_MS, self._refresh_dashboard)

    def _update_tiles(self):
        """Push latest values from _latest_row into the tile labels."""
        with self._lock:
            row = dict(self._latest_row)

        for name, lbl in self._value_labels.items():
            if name not in row:
                continue
            val = row[name]
            if val is None:
                text = "N/A"
                fg = C_YELLOW
            elif isinstance(val, float):
                text = f"{val:.2f}"
                fg = C_BLUE
            elif isinstance(val, int):
                text = str(val)
                fg = C_BLUE
            else:
                text = str(val)
                fg = C_TEXT
            try:
                lbl.config(text=text, fg=fg)
            except tk.TclError:
                pass  # widget may have been destroyed during rebuild

        # Update recording info in status bar
        if self._logging_active and self._log_filepath:
            ts = row.get("Timestamp", "")
            self._rec_info_var.set(f"● REC  {ts}  → {os.path.basename(self._log_filepath)}")

    # ------------------------------------------------------------------
    # CSV Recording
    # ------------------------------------------------------------------

    def _start_recording(self):
        selected = self._get_selected_params()
        if not selected:
            messagebox.showwarning("No Sensors", "Please select at least one sensor to record.")
            return
        if not self.pydabaus:
            messagebox.showerror("Not Connected", "Please wait for ECU connection.")
            return

        # Ask for output path
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"bmw_log_{ts}.csv"
        filepath = filedialog.asksaveasfilename(
            title="Save CSV Log As",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not filepath:
            return

        self._log_filepath = filepath
        self.pydabaus.selected_params = list(selected)
        self._logging_active = True

        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._rec_badge.config(text=" ● RECORDING ", fg=C_RED)

        self._log_thread = threading.Thread(
            target=self.pydabaus.log_to_csv,
            kwargs={
                "filepath": filepath,
                "interval_ms": 250,
                "duration_s": 0,
                "callback": self._on_log_row,
            },
            daemon=True,
        )
        self._log_thread.start()
        self._set_status(f"Recording to {os.path.basename(filepath)}")

    def _on_log_row(self, row: dict):
        """Callback invoked by PYDABAUS.log_to_csv per sweep (runs in log thread)."""
        with self._lock:
            self._latest_row = row

    def _stop_recording(self):
        self._logging_active = False
        # Clearing selected_params causes PYDABAUS.log_to_csv to return on the
        # next sweep (it logs a warning and exits when the list is empty).
        if self.pydabaus:
            self.pydabaus.selected_params = []

        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._rec_badge.config(text="")
        self._rec_info_var.set("")
        saved = self._log_filepath
        self._log_filepath = None
        self._set_status(
            f"Recording stopped. Log saved to: {saved}" if saved else "Recording stopped."
        )

    # ------------------------------------------------------------------
    # Sensor availability test dialog
    # ------------------------------------------------------------------

    def _run_sensor_test_dialog(self):
        if not self.pydabaus:
            messagebox.showerror("Not Connected", "Please wait for ECU connection.")
            return

        win = tk.Toplevel(self.root)
        win.title("Sensor Availability Test")
        win.configure(bg=C_BG)
        win.geometry("680x520")
        win.grab_set()

        tk.Label(
            win,
            text="Sensor Availability Test",
            bg=C_BG,
            fg=C_HEADER,
            font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
        ).pack(pady=(12, 4))

        tk.Label(
            win,
            text="Probing all ECU parameters. Missing sensors are logged as errors.",
            bg=C_BG,
            fg=C_TEXT_DIM,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
        ).pack(pady=(0, 8))

        # Progress bar
        prog_var = tk.DoubleVar(value=0)
        prog_lbl_var = tk.StringVar(value="Starting…")
        tk.Label(
            win, textvariable=prog_lbl_var, bg=C_BG, fg=C_TEXT,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
        ).pack()
        prog = ttk.Progressbar(win, variable=prog_var, maximum=100, length=580)
        prog.pack(pady=6)

        # Results text area
        result_frame = tk.Frame(win, bg=C_PANEL)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        txt = tk.Text(
            result_frame,
            bg=C_PANEL,
            fg=C_TEXT,
            font=(FONT_FAMILY, FONT_SIZE_SMALL),
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        sb = tk.Scrollbar(result_frame, command=txt.yview)
        txt.config(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(fill=tk.BOTH, expand=True)

        def _append(text, tag=None):
            txt.config(state=tk.NORMAL)
            if tag:
                txt.insert(tk.END, text + "\n", tag)
            else:
                txt.insert(tk.END, text + "\n")
            txt.see(tk.END)
            txt.config(state=tk.DISABLED)

        txt.tag_config("ok", foreground=C_GREEN)
        txt.tag_config("err", foreground=C_RED)
        txt.tag_config("hdr", foreground=C_HEADER, font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"))

        # Close button (disabled until test completes)
        close_btn = tk.Button(
            win,
            text="Close",
            command=win.destroy,
            bg=C_BTN,
            fg=C_TEXT,
            state=tk.DISABLED,
            relief=tk.FLAT,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL),
            padx=16,
            pady=4,
            cursor="hand2",
        )
        close_btn.pack(pady=8)

        total_params = diag.TOTAL_PARAMETER_COUNT

        def _progress(current, total, name):
            pct = current * 100.0 / total
            win.after(0, prog_var.set, pct)
            win.after(0, prog_lbl_var.set, f"Testing {current}/{total}: {name}")

        def _done(results):
            available = [n for n, v in results.items() if v["available"]]
            missing = [(n, v["error"]) for n, v in results.items() if not v["available"]]

            win.after(0, _append, f"\n{'='*60}", "hdr")
            win.after(0, _append, f"RESULTS: {len(available)}/{total_params} sensors responded", "hdr")
            win.after(0, _append, f"{'='*60}", "hdr")

            if missing:
                win.after(0, _append, f"\n⚠  {len(missing)} MISSING / UNAVAILABLE SENSORS:", "err")
                for name, err in missing:
                    win.after(0, _append, f"  ✗ {name}  –  {err}", "err")
            else:
                win.after(0, _append, "\n✓ All sensors responded!", "ok")

            win.after(0, _append, f"\n{'─'*60}")
            win.after(0, _append, f"✓ Available ({len(available)}):", "ok")
            for name in available:
                win.after(0, _append, f"  ✓ {name}", "ok")

            win.after(0, prog_lbl_var.set, "Test complete.")
            win.after(0, close_btn.config, {"state": tk.NORMAL})
            win.after(0, _append, "\nFull error details written to the application log.")

        _append("Starting sensor availability test…")

        tester = SensorAvailabilityTester(self.pydabaus)
        tester.run_in_thread(
            progress_callback=_progress,
            done_callback=_done,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str):
        try:
            self._status_var.set(msg)
        except tk.TclError:
            pass


# ============================================================================
# CLI entry point
# ============================================================================


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BMW E90 N46B20B – ECU Diagnostics GUI Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in offline demo mode (no hardware required)",
    )
    parser.add_argument(
        "--interface", "-i", default="pcan",
        help="CAN interface type: pcan, kvaser, vector, ixxat, slcan, kdcan, socketcan",
    )
    parser.add_argument(
        "--channel", "-c", default="PCAN_USBBUS1",
        help="CAN channel (default: PCAN_USBBUS1)",
    )
    parser.add_argument(
        "--port", "-p", default=None,
        help="Serial port for K+DCAN cable (e.g. COM3). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--bitrate", "-b", type=int, default=diag.DCAN_BITRATE,
        help=f"CAN bus bitrate (default: {diag.DCAN_BITRATE})",
    )
    return parser


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = build_argument_parser()
    args = parser.parse_args()

    root = tk.Tk()
    app = BmwDiagGUI(root, args)  # noqa: F841
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
