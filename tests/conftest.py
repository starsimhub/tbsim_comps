"""Pytest configuration for the tbsim validation harness."""

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "tbsim_bug: upstream tbsim defect; expected to fail until fixed (see findings/TBSIM_KNOWN_BUGS.md)",
    )
