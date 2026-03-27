"""Auto-commit utility for the research/ sub-repo."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def commit_research(research_dir: Path, message: str) -> bool:
    """Stage all changes and commit in the research sub-repo.

    Returns True if a commit was created, False otherwise.
    Never raises — failures are logged as warnings.
    """
    try:
        repo = str(research_dir)
        subprocess.run(
            ["git", "add", "."],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
        # Check if there's anything staged
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo, capture_output=True, timeout=10,
        )
        if status.returncode == 0:
            logger.debug("research_git: nothing to commit")
            return False
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"research_git: committed — {message}")
            return True
        logger.warning(f"research_git: commit failed — {result.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"research_git: error — {e}")
        return False
