"""
Tests for BMW E90 320i N46B20B Diagnostics & Data Logger.

These tests validate the parameter catalogue, decoders, PYDABAUS layer,
and CLI helpers without requiring any hardware.
"""

import csv
import os
import sys
import tempfile

import pytest

# Ensure the repo root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bmw_e90_diagnostics as diag


# ──────────────────────────────────────────────────────────────────────────────
# Parameter catalogue integrity
# ──────────────────────────────────────────────────────────────────────────────


class TestParameterCatalogue:
    """Verify the parameter catalogue is complete and consistent."""

    def test_catalogue_not_empty(self):
        assert len(diag._PARAMETER_CATALOGUE) > 0

    def test_total_count_matches(self):
        assert diag.TOTAL_PARAMETER_COUNT == len(diag._PARAMETER_CATALOGUE)

    def test_all_required_keys_present(self):
        required_keys = {"did", "name", "unit", "description", "decoder", "category"}
        for idx, param in enumerate(diag._PARAMETER_CATALOGUE):
            missing = required_keys - param.keys()
            assert not missing, f"Param #{idx + 1} ({param.get('name')}) missing keys: {missing}"

    def test_all_decoders_exist(self):
        for param in diag._PARAMETER_CATALOGUE:
            assert param["decoder"] in diag._DECODERS, (
                f"Decoder '{param['decoder']}' for {param['name']} not in _DECODERS"
            )

    def test_no_duplicate_names(self):
        names = [p["name"] for p in diag._PARAMETER_CATALOGUE]
        assert len(names) == len(set(names)), "Duplicate parameter names found"

    def test_no_duplicate_dids(self):
        dids = [p["did"] for p in diag._PARAMETER_CATALOGUE]
        assert len(dids) == len(set(dids)), "Duplicate DIDs found"

    def test_categories_not_empty(self):
        categories = {p["category"] for p in diag._PARAMETER_CATALOGUE}
        assert len(categories) >= 10, f"Expected 10+ categories, got {len(categories)}"


# ──────────────────────────────────────────────────────────────────────────────
# Decoders
# ──────────────────────────────────────────────────────────────────────────────


class TestDecoders:
    """Validate decoder functions produce correct engineering values."""

    def test_decode_rpm(self):
        # 0x0C 0x00 → (3072) / 4 = 768 RPM
        assert diag._decode_rpm(bytes([0x0C, 0x00])) == 768.0

    def test_decode_rpm_zero(self):
        assert diag._decode_rpm(bytes([0x00, 0x00])) == 0.0

    def test_decode_rpm_short_data(self):
        assert diag._decode_rpm(bytes([0x0C])) == 0.0

    def test_decode_percent(self):
        assert diag._decode_percent(bytes([0xFF])) == pytest.approx(100.0, abs=0.01)
        assert diag._decode_percent(bytes([0x00])) == 0.0

    def test_decode_percent_empty(self):
        assert diag._decode_percent(b"") == 0.0

    def test_decode_temp(self):
        # 0 → -40°C, 40 → 0°C, 200 → 160°C
        assert diag._decode_temp(bytes([0])) == -40.0
        assert diag._decode_temp(bytes([40])) == 0.0
        assert diag._decode_temp(bytes([200])) == 160.0

    def test_decode_temp_empty(self):
        assert diag._decode_temp(b"") == -40.0

    def test_decode_temp16(self):
        # (0x01, 0xF4) = 500 → 500/10 - 40 = 10.0°C
        assert diag._decode_temp16(bytes([0x01, 0xF4])) == pytest.approx(10.0)

    def test_decode_fuel_trim(self):
        # 128 → 0%, 0 → -100%, 255 → ~99.2%
        assert diag._decode_fuel_trim(bytes([128])) == 0.0
        assert diag._decode_fuel_trim(bytes([0])) == -100.0
        assert diag._decode_fuel_trim(bytes([255])) == pytest.approx(99.2, abs=0.2)

    def test_decode_timing(self):
        # 128 → 0°, 0 → -64°, 255 → 63.5°
        assert diag._decode_timing(bytes([128])) == 0.0
        assert diag._decode_timing(bytes([0])) == -64.0

    def test_decode_maf(self):
        # (0x01, 0x00) = 256 → 256/100 = 2.56 g/s
        assert diag._decode_maf(bytes([0x01, 0x00])) == pytest.approx(2.56)

    def test_decode_speed(self):
        assert diag._decode_speed(bytes([120])) == 120.0
        assert diag._decode_speed(bytes([0])) == 0.0

    def test_decode_voltage(self):
        assert diag._decode_voltage(bytes([0xFF])) == pytest.approx(5.0, abs=0.1)
        assert diag._decode_voltage(bytes([0x00])) == 0.0

    def test_decode_bool_byte(self):
        assert diag._decode_bool_byte(bytes([0])) == 0
        assert diag._decode_bool_byte(bytes([1])) == 1
        assert diag._decode_bool_byte(bytes([0xFF])) == 1

    def test_decode_gear(self):
        assert diag._decode_gear(bytes([0])) == "N"
        assert diag._decode_gear(bytes([3])) == "3"
        assert diag._decode_gear(bytes([0xFF])) == "R"
        assert diag._decode_gear(bytes([7])) == "R"

    def test_decode_ascii(self):
        assert diag._decode_ascii(b"MSV70\x00") == "MSV70"

    def test_decode_hex32(self):
        result = diag._decode_hex32(bytes([0x00, 0x00, 0x00, 0xFF]))
        assert result == "0x000000FF"

    def test_decode_hex8(self):
        assert diag._decode_hex8(bytes([0xAB])) == "0xAB"

    def test_decode_knock_retard(self):
        assert diag._decode_knock_retard(bytes([8])) == 2.0

    def test_decode_lambda_val(self):
        # 32768 → 1.0 lambda
        assert diag._decode_lambda_val(bytes([0x80, 0x00])) == 1.0

    def test_decode_vanos_angle(self):
        # (0x01, 0xF4) = 500 → 500/10 - 50 = 0.0
        assert diag._decode_vanos_angle(bytes([0x01, 0xF4])) == pytest.approx(0.0)

    def test_decode_oil_level_signed(self):
        # 200 → 200-256 = -56
        assert diag._decode_oil_level(bytes([200])) == -56.0
        assert diag._decode_oil_level(bytes([10])) == 10.0

    def test_decode_steering_angle(self):
        # (0x80, 0x00) = 32768 → 32768/10 - 3276.8 = 0.0
        assert diag._decode_steering_angle(bytes([0x80, 0x00])) == pytest.approx(0.0)

    def test_decode_parameter_function(self):
        """Test the high-level decode_parameter function."""
        param = {"did": 0xF40C, "name": "Engine_RPM", "decoder": "rpm", "unit": "rpm"}
        result = diag.decode_parameter(param, bytes([0x0C, 0x00]))
        assert result == 768.0


# ──────────────────────────────────────────────────────────────────────────────
# PYDABAUS layer
# ──────────────────────────────────────────────────────────────────────────────


class TestPYDABAUS:
    """Test the PYDABAUS automation layer."""

    @pytest.fixture
    def demo_client(self):
        return diag.OfflineDemoClient()

    @pytest.fixture
    def pydabaus(self, demo_client):
        return diag.PYDABAUS(demo_client)

    def test_get_all_parameters(self, pydabaus):
        params = pydabaus.get_all_parameters()
        assert len(params) == diag.TOTAL_PARAMETER_COUNT

    def test_get_categories(self, pydabaus):
        cats = pydabaus.get_categories()
        assert len(cats) >= 10
        assert all(isinstance(c, str) for c in cats)

    def test_get_parameters_by_category(self, pydabaus):
        params = pydabaus.get_parameters_by_category("Temperatures")
        assert len(params) > 0
        assert all(p["category"] == "Temperatures" for p in params)

    def test_select_all(self, pydabaus):
        selected = pydabaus.select_all_parameters()
        assert len(selected) == diag.TOTAL_PARAMETER_COUNT
        assert pydabaus.selected_params == selected

    def test_select_by_index(self, pydabaus):
        selected = pydabaus.select_parameters([1, 2, 3])
        assert len(selected) == 3
        assert selected[0] == diag._PARAMETER_CATALOGUE[0]

    def test_select_by_index_out_of_range(self, pydabaus):
        selected = pydabaus.select_parameters([0, 9999])
        assert len(selected) == 0

    def test_select_categories(self, pydabaus):
        selected = pydabaus.select_categories(["Temperatures", "VANOS"])
        assert len(selected) > 0
        assert all(p["category"] in ("Temperatures", "VANOS") for p in selected)

    def test_read_parameter_demo(self, pydabaus):
        param = diag._PARAMETER_CATALOGUE[0]
        name, value, unit, raw_hex = pydabaus.read_parameter(param)
        assert name == param["name"]
        assert unit == param["unit"]
        # Demo mode returns random data, so value should not be None
        assert value is not None

    def test_read_all_selected_demo(self, pydabaus):
        pydabaus.select_parameters([1, 2, 3])
        results = pydabaus.read_all_selected()
        assert len(results) == 3
        for name, value, unit, raw_hex in results:
            assert isinstance(name, str)
            assert value is not None

    def test_log_to_csv_demo(self, pydabaus):
        pydabaus.select_parameters([1, 2, 3])
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            pydabaus.log_to_csv(tmp_path, interval_ms=50, duration_s=0.3)

            # Verify CSV was written
            assert os.path.exists(tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) >= 1
            assert "Timestamp" in rows[0]
            # Check parameter columns exist
            assert diag._PARAMETER_CATALOGUE[0]["name"] in rows[0]
        finally:
            os.unlink(tmp_path)

    def test_log_no_params_selected(self, pydabaus):
        """Logging with no parameters selected should return immediately."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp:
            tmp_path = tmp.name
        try:
            pydabaus.log_to_csv(tmp_path, interval_ms=50, duration_s=0.1)
            # File may or may not exist, but no crash
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


# ──────────────────────────────────────────────────────────────────────────────
# CLI helpers
# ──────────────────────────────────────────────────────────────────────────────


class TestCLIHelpers:
    """Test CLI utility functions."""

    def test_parse_number_list_simple(self):
        assert diag._parse_number_list("1,2,3") == [1, 2, 3]

    def test_parse_number_list_ranges(self):
        assert diag._parse_number_list("1-5") == [1, 2, 3, 4, 5]

    def test_parse_number_list_mixed(self):
        result = diag._parse_number_list("1-3,7,10-12")
        assert result == [1, 2, 3, 7, 10, 11, 12]

    def test_parse_number_list_dedup_and_sort(self):
        result = diag._parse_number_list("5,3,1,3,5")
        assert result == [1, 3, 5]

    def test_parse_number_list_empty(self):
        assert diag._parse_number_list("") == []

    def test_parse_number_list_invalid(self):
        assert diag._parse_number_list("abc,def") == []

    def test_parse_number_list_mixed_invalid(self):
        result = diag._parse_number_list("1,abc,3")
        assert result == [1, 3]

    def test_build_argument_parser(self):
        parser = diag.build_argument_parser()
        args = parser.parse_args(["--demo", "--log-all"])
        assert args.demo is True
        assert args.log_all is True
        assert args.rate == 100

    def test_argument_parser_defaults(self):
        parser = diag.build_argument_parser()
        args = parser.parse_args([])
        assert args.interface == "pcan"
        assert args.bitrate == 500000
        assert args.duration == 0
        assert args.demo is False


# ──────────────────────────────────────────────────────────────────────────────
# OfflineDemoClient
# ──────────────────────────────────────────────────────────────────────────────


class TestOfflineDemoClient:
    """Test the offline demo client."""

    def test_connect(self):
        client = diag.OfflineDemoClient()
        assert client.connect() is True
        assert client.is_connected is True

    def test_disconnect(self):
        client = diag.OfflineDemoClient()
        client.disconnect()
        assert client.is_connected is False

    def test_read_did_returns_bytes(self):
        client = diag.OfflineDemoClient()
        data = client.read_did(0xF40C)
        assert isinstance(data, bytes)
        assert len(data) >= 1

    def test_tester_present(self):
        client = diag.OfflineDemoClient()
        assert client.send_tester_present() is True


# ──────────────────────────────────────────────────────────────────────────────
# Protocol constants
# ──────────────────────────────────────────────────────────────────────────────


class TestProtocolConstants:
    """Verify protocol constants are correct for BMW E90."""

    def test_dcan_bitrate(self):
        assert diag.DCAN_BITRATE == 500000

    def test_dme_request_id(self):
        assert diag.DME_REQUEST_ID == 0x612

    def test_dme_response_id(self):
        assert diag.DME_RESPONSE_ID == 0x61A

    def test_uds_service_ids(self):
        assert diag.UDS_READ_DATA_BY_IDENTIFIER == 0x22
        assert diag.UDS_TESTER_PRESENT == 0x3E
        assert diag.UDS_DIAGNOSTIC_SESSION_CONTROL == 0x10
