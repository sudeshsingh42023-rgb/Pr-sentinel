from pr_sentinel.diffing import parse_unified_diff, scope_summary, render_diff_for_prompt

DIFF = '''diff --git a/a.py b/a.py
index 111..222 100644
--- a/a.py
+++ b/a.py
@@ -1,3 +1,5 @@
 def f():
-    return 1
+    return 2
+
+def g():
+    return 3
'''


def test_parse_unified_diff_counts_files():
    files = parse_unified_diff(DIFF)
    assert len(files) == 1
    assert files[0].path == "a.py"


def test_parse_unified_diff_counts_added_removed():
    files = parse_unified_diff(DIFF)
    f = files[0]
    assert f.added_lines() == 4  # "return 2", blank line, "def g():", "return 3"
    assert f.removed_lines() == 1


def test_scope_summary():
    files = parse_unified_diff(DIFF)
    summary = scope_summary(files)
    assert summary["files_changed"] == 1
    assert summary["lines_added"] == 4
    assert summary["lines_removed"] == 1


def test_render_diff_truncates_when_too_long():
    files = parse_unified_diff(DIFF)
    rendered = render_diff_for_prompt(files, max_chars=10)
    assert "truncated" in rendered
    assert len(rendered) < 200


def test_new_file_status():
    diff = '''diff --git a/new.py b/new.py
new file mode 100644
index 000..111
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+x = 1
+y = 2
'''
    files = parse_unified_diff(diff)
    assert files[0].status == "added"
    assert files[0].added_lines() == 2
