"""Optional Git provenance for runnable source archives."""
from pathlib import Path
import subprocess


def optional_git_sha(root: Path) -> str | None:
    """Return this checkout's HEAD if available; callers must also hash source."""
    # An archive may sit inside an unrelated repository. Do not claim its HEAD.
    if not (root / ".git").exists():
        return None
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                       text=True, stderr=subprocess.DEVNULL).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None
