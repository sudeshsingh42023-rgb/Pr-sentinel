from pr_sentinel.agents.security_agent import _prescan_secrets

DIFF_WITH_KEY = '''diff --git a/a.py b/a.py
+api_key = "sk-live-51H8xJ2KZ9mQwErTyU1234567890abcd"
'''

DIFF_WITH_AWS_KEY = '''diff --git a/a.py b/a.py
+AWS_KEY = "AKIAABCDEFGHIJKLMNOP"
'''

DIFF_CLEAN = '''diff --git a/a.py b/a.py
+def add(a, b):
+    return a + b
'''


def test_prescan_detects_generic_api_key():
    findings = _prescan_secrets(DIFF_WITH_KEY)
    assert any(f.category == "secret" for f in findings)


def test_prescan_detects_aws_key():
    findings = _prescan_secrets(DIFF_WITH_AWS_KEY)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_prescan_no_false_positive_on_clean_diff():
    findings = _prescan_secrets(DIFF_CLEAN)
    assert findings == []
