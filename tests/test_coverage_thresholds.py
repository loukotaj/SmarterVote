import json

from scripts.check_coverage_thresholds import check_report


def test_check_report_normalizes_windows_paths(tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps({"files": {"pkg\\module.py": {"summary": {"percent_covered": 75.0}}}}),
        encoding="utf-8",
    )

    assert check_report(report, {"pkg/module.py": 70.0}) == []


def test_check_report_reports_missing_and_undercovered_files(tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps({"files": {"pkg/module.py": {"summary": {"percent_covered": 49.9}}}}),
        encoding="utf-8",
    )

    failures = check_report(report, {"pkg/module.py": 50.0, "pkg/missing.py": 1.0})

    assert failures == [
        "pkg/module.py: 49.9% is below 50.0%",
        "pkg/missing.py: missing from coverage report",
    ]
