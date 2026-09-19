from pr_sentinel.config import Settings, severity_at_least


def test_default_settings_load():
    s = Settings.load()
    assert s.gate.block_severity == "high"


def test_severity_at_least():
    assert severity_at_least("critical", "high")
    assert severity_at_least("high", "high")
    assert not severity_at_least("medium", "high")
