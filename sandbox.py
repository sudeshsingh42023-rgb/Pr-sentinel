"""Sandboxed execution of correctness-agent-proposed tests.

Runs proposed pytest snippets in a subprocess with a hard timeout, on a
temporary copy of the repo. This is a *quality gate*, not a security sandbox --
it protects CI from an infinite loop or a hung process, not from malicious code.
If you need to run untrusted code safely, put this behind a container or gVisor,
not a bare subprocess; that limitation is called out in the README on purpose.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SandboxResult:
    passed: bool
    stdout: str
    stderr: str
    timed_out: bool
    returncode: int | None


def run_proposed_test(
    repo_dir: str | Path, test_code: str, timeout_s: int = 60
) -> SandboxResult:
    repo_dir = Path(repo_dir)
    with tempfile.TemporaryDirectory(prefix="sentinel-sandbox-") as tmp:
        tmp_path = Path(tmp)
        # Copy the repo so a failing/destructive test can't touch the real tree.
        shutil.copytree(repo_dir, tmp_path / "repo", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"))
        test_file = tmp_path / "repo" / "test_sentinel_proposed.py"
        test_file.write_text(test_code)

        try:
            proc = subprocess.run(
                ["python", "-m", "pytest", str(test_file), "-q", "--no-header"],
                cwd=tmp_path / "repo",
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            return SandboxResult(
                passed=proc.returncode == 0,
                stdout=proc.stdout[-4000:],
                stderr=proc.stderr[-4000:],
                timed_out=False,
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                passed=False,
                stdout=(exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                stderr=f"timed out after {timeout_s}s",
                timed_out=True,
                returncode=None,
            )
