"""Tests for CLI default export behavior."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from open_credit_evidence.cli import DEFAULT_REPORTS_DIR, app

runner = CliRunner()


class TestProcessDefaultExport:
    """Tests for default report export behavior."""

    def test_process_exports_to_default_path(
        self, sample_case_001_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Process should save report to reports/<case_id>.json by default."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["process", str(sample_case_001_dir), "--skip-api"])

        assert result.exit_code == 0
        assert "Report saved to" in result.stdout

        reports_dir = tmp_path / "reports"
        assert reports_dir.exists()

        report_files = list(reports_dir.glob("*.json"))
        assert len(report_files) == 1

        report_path = report_files[0]
        assert "LOAN-2026-09-001" in report_path.name

        report_data = json.loads(report_path.read_text())
        assert "report_id" in report_data
        assert "chain_fingerprint" in report_data

    def test_process_no_export_skips_file_output(
        self, sample_case_001_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Process with --no-export should not write any files."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["process", str(sample_case_001_dir), "--skip-api", "--no-export"]
        )

        assert result.exit_code == 0
        assert "Report export skipped" in result.stdout

        reports_dir = tmp_path / "reports"
        assert not reports_dir.exists() or len(list(reports_dir.glob("*.json"))) == 0

    def test_process_custom_output_path(
        self, sample_case_001_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Process with -o should use custom output path."""
        monkeypatch.chdir(tmp_path)
        custom_path = tmp_path / "custom" / "my_report.json"

        result = runner.invoke(
            app, ["process", str(sample_case_001_dir), "--skip-api", "-o", str(custom_path)]
        )

        assert result.exit_code == 0
        assert "Report saved to" in result.stdout
        assert custom_path.exists()

        report_data = json.loads(custom_path.read_text())
        assert "report_id" in report_data

    def test_process_output_overrides_default(
        self, sample_case_001_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Process with -o should not create default reports/ directory."""
        monkeypatch.chdir(tmp_path)
        custom_path = tmp_path / "my_report.json"

        result = runner.invoke(
            app, ["process", str(sample_case_001_dir), "--skip-api", "-o", str(custom_path)]
        )

        assert result.exit_code == 0
        assert custom_path.exists()

        reports_dir = tmp_path / "reports"
        assert not reports_dir.exists()

    def test_default_reports_dir_constant(self) -> None:
        """DEFAULT_REPORTS_DIR should be 'reports'."""
        assert Path("reports") == DEFAULT_REPORTS_DIR


class TestProcessIdempotent:
    """Tests for report overwrite behavior."""

    def test_process_overwrites_existing_report(
        self, sample_case_001_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Running process twice should overwrite the report."""
        monkeypatch.chdir(tmp_path)

        result1 = runner.invoke(app, ["process", str(sample_case_001_dir), "--skip-api"])
        assert result1.exit_code == 0

        reports_dir = tmp_path / "reports"
        report_files = list(reports_dir.glob("*.json"))
        assert len(report_files) == 1
        first_report = json.loads(report_files[0].read_text())

        result2 = runner.invoke(app, ["process", str(sample_case_001_dir), "--skip-api"])
        assert result2.exit_code == 0

        report_files = list(reports_dir.glob("*.json"))
        assert len(report_files) == 1
        second_report = json.loads(report_files[0].read_text())

        assert first_report["report_id"] != second_report["report_id"]
