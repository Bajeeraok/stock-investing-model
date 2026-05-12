"""Tests for signals.confidence_calibration module."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from signals.confidence_calibration import (
    CalibrationReport,
    build_calibration_report,
    calibration_report_to_dict,
)


def _make_data_root(ft_records: list[dict] | None = None) -> Path:
    """Create a temp data root with forward_tracking.json."""
    root = Path(tempfile.mkdtemp())
    if ft_records is not None:
        with open(root / "forward_tracking.json", "w", encoding="utf-8") as f:
            json.dump({"records": ft_records}, f)
    return root


class TestBuildCalibrationReport:
    def test_empty_data(self):
        root = _make_data_root(ft_records=[])
        report = build_calibration_report(root)
        assert isinstance(report, CalibrationReport)
        assert len(report.buckets) == 0
        assert "Insufficient" in report.note

    def test_sufficient_data(self):
        records = []
        for i in range(50):
            conf = 20 + i  # range 20..69 covers multiple buckets
            ret = (conf - 40) * 0.1 + 1
            records.append({
                "confidence_pct": conf,
                "return_20d_pct": ret,
            })
        root = _make_data_root(ft_records=records)
        report = build_calibration_report(root)
        assert isinstance(report, CalibrationReport)
        assert report.total_observations == 50
        assert len(report.buckets) > 0

    def test_monotonic_data(self):
        records = []
        for bucket_conf, bucket_ret in [(25, -2), (45, 0.5), (65, 3), (80, 6), (92, 10)]:
            for _ in range(10):
                records.append({
                    "confidence_pct": bucket_conf + 1,
                    "return_20d_pct": bucket_ret + 0.5,
                })
        root = _make_data_root(ft_records=records)
        report = build_calibration_report(root)
        assert report.total_observations == 50
        assert len(report.buckets) >= 3

    def test_serialization(self):
        records = []
        for i in range(20):
            records.append({
                "confidence_pct": 40 + i * 2,
                "return_20d_pct": i * 0.5,
            })
        root = _make_data_root(ft_records=records)
        report = build_calibration_report(root)
        d = calibration_report_to_dict(report)
        assert "buckets" in d
        assert "total_observations" in d
        assert "calibration_error" in d
        assert "note" in d

    def test_custom_bucket_edges(self):
        records = [{"confidence_pct": 50 + i, "return_20d_pct": i * 0.3} for i in range(20)]
        root = _make_data_root(ft_records=records)
        report = build_calibration_report(root, bucket_edges=[0, 50, 75, 100])
        assert len(report.buckets) >= 1
