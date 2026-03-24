"""
Unit tests for monitor.model.parameters (ParameterDescriptor + ParameterModel)
These tests do NOT require a Qt application.
"""

import struct
import pytest

from monitor.model.parameters import (
    ParameterDescriptor, ParameterModel, ParamType, ParamFlags,
    default_parameter_table,
)


# ── ParameterDescriptor ───────────────────────────────────────────────────────
class TestParameterDescriptor:
    def _f32(self, **kw) -> ParameterDescriptor:
        defaults = dict(
            param_id=1, type=ParamType.F32, flags=0,
            min_value=0.0, max_value=10.0, default_value=1.0,
            name="test.param", unit="", group="test"
        )
        defaults.update(kw)
        return ParameterDescriptor(**defaults)

    def test_encode_decode_f32(self):
        d = self._f32()
        encoded = d.encode_value(3.14)
        decoded = d.decode_value(encoded)
        assert abs(decoded - 3.14) < 1e-5

    def test_encode_decode_i32(self):
        d = ParameterDescriptor(
            param_id=2, type=ParamType.I32, flags=0,
            min_value=-1000, max_value=1000, default_value=0,
            name="x", unit="", group="g"
        )
        encoded = d.encode_value(-42)
        decoded = d.decode_value(encoded)
        assert int(decoded) == -42

    def test_encode_decode_bool_true(self):
        d = ParameterDescriptor(
            param_id=3, type=ParamType.BOOL, flags=0,
            min_value=0, max_value=1, default_value=0,
            name="flag", unit="", group="g"
        )
        encoded = d.encode_value(1.0)
        decoded = d.decode_value(encoded)
        assert decoded == 1.0

    def test_encode_decode_bool_false(self):
        d = ParameterDescriptor(
            param_id=3, type=ParamType.BOOL, flags=0,
            min_value=0, max_value=1, default_value=0,
            name="flag", unit="", group="g"
        )
        encoded = d.encode_value(0.0)
        decoded = d.decode_value(encoded)
        assert decoded == 0.0

    def test_validate_in_range(self):
        d = self._f32(min_value=0.0, max_value=5.0)
        assert d.validate(2.5) is True
        assert d.validate(0.0) is True
        assert d.validate(5.0) is True

    def test_validate_out_of_range(self):
        d = self._f32(min_value=0.0, max_value=5.0)
        assert d.validate(-0.1) is False
        assert d.validate(5.001) is False

    def test_read_only_flag(self):
        d = self._f32(flags=ParamFlags.READ_ONLY)
        assert d.read_only is True

    def test_persistent_flag(self):
        d = self._f32(flags=ParamFlags.PERSISTENT)
        assert d.persistent is True

    def test_no_flags(self):
        d = self._f32(flags=0)
        assert d.read_only is False
        assert d.persistent is False

    def test_decode_too_short_raises(self):
        d = self._f32()
        with pytest.raises(ValueError):
            d.decode_value(b"\x01")  # only 1 byte for f32 that needs 4

    def test_u8_encode_decode(self):
        d = ParameterDescriptor(
            param_id=5, type=ParamType.U8, flags=0,
            min_value=0, max_value=255, default_value=0,
            name="u", unit="", group="g"
        )
        assert int(d.decode_value(d.encode_value(200))) == 200


# ── default_parameter_table ───────────────────────────────────────────────────
class TestDefaultParameterTable:
    def test_non_empty(self):
        table = default_parameter_table()
        assert len(table) > 0

    def test_unique_ids(self):
        table = default_parameter_table()
        ids   = [d.param_id for d in table]
        assert len(ids) == len(set(ids)), "Duplicate param_id in default table"

    def test_unique_names(self):
        table = default_parameter_table()
        names = [d.name for d in table]
        assert len(names) == len(set(names)), "Duplicate name in default table"

    def test_all_defaults_in_range(self):
        table = default_parameter_table()
        for d in table:
            assert d.validate(d.default_value), \
                f"{d.name}: default {d.default_value} not in [{d.min_value}, {d.max_value}]"

    def test_groups_present(self):
        table  = default_parameter_table()
        groups = {d.group for d in table}
        assert "control.angle"    in groups
        assert "control.velocity" in groups
        assert "safety"           in groups
        assert "imu"              in groups
        assert "robot"            in groups

    def test_pid_kp_gains_exist(self):
        table = default_parameter_table()
        names = {d.name for d in table}
        assert "angle.kp"    in names
        assert "velocity.kp" in names
        assert "yaw.kp"      in names


# ── ParameterModel (Qt-free subset) ──────────────────────────────────────────
# We test the non-Qt logic by calling internal methods directly.
# A full Qt model test would require pytest-qt; we keep these headless.
class TestParameterModelHeadless:
    def setup_method(self):
        # ParameterModel inherits QAbstractItemModel; we need a QApplication.
        # Create a minimal one only once (pytest-qt would handle this).
        import sys
        try:
            from PySide6.QtWidgets import QApplication
            if QApplication.instance() is None:
                self._app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            pytest.skip("Qt not available in this environment")
        self.model = ParameterModel()

    def test_get_all_values_returns_dict(self):
        values = self.model.get_all_values()
        assert isinstance(values, dict)
        assert "angle.kp" in values

    def test_default_values_match_descriptors(self):
        table  = default_parameter_table()
        values = self.model.get_all_values()
        for desc in table:
            assert desc.name in values
            assert abs(values[desc.name] - desc.default_value) < 1e-6, \
                f"{desc.name}: model default {values[desc.name]} != descriptor default {desc.default_value}"

    def test_update_from_firmware_changes_value(self):
        self.model.update_from_firmware(0x0001, 3.14)
        values = self.model.get_all_values()
        assert abs(values["angle.kp"] - 3.14) < 1e-5

    def test_mark_nack_reverts_to_confirmed(self):
        # Confirm value is 1.0 (default)
        self.model.update_from_firmware(0x0001, 1.0)
        # Simulate a local edit
        node = self.model._id_to_node[0x0001]
        node.current_value = 99.0
        node.pending       = True
        # NACK reverts
        self.model.mark_nack(0x0001)
        assert abs(node.current_value - 1.0) < 1e-5
        assert node.pending is False

    def test_unknown_param_id_ignored(self):
        # Should not raise
        self.model.update_from_firmware(0xFFFF, 0.0)
        self.model.mark_nack(0xFFFF)
