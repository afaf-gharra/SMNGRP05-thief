"""Which commit is actually playing (mandatory rule 53).

Teams may improve their code between matches — that is expressly allowed — but
every match must record the exact commit that played it, so the examiner can
check out that revision and reproduce the result rather than whatever happens to
be on the branch tip weeks later.

The hash is sealed into the step-zero record, so it is fixed before the first
move and cannot be back-dated. A dirty working tree is reported as such: a match
played on uncommitted code is not reproducible, and saying so is more useful
than quietly reporting the last clean hash.
"""

import subprocess
from functools import lru_cache
from pathlib import Path

UNKNOWN = "unknown"


def _git(*args: str, cwd: Path | None = None) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


@lru_cache(maxsize=4)
def commit_hash(repo: str | None = None, short: bool = False) -> str:
    """The current commit hash, suffixed ``-dirty`` when the tree has changes."""
    cwd = Path(repo) if repo else None
    args = ("rev-parse", "--short", "HEAD") if short else ("rev-parse", "HEAD")
    head = _git(*args, cwd=cwd)
    if not head:
        return UNKNOWN
    status = _git("status", "--porcelain", cwd=cwd)
    return f"{head}-dirty" if status else head


@lru_cache(maxsize=4)
def commit_sha(repo: str | None = None) -> str:
    """The bare 40-character commit hash, with no ``-dirty`` suffix.

    The handshake identity needs a hash an opponent can hand straight to
    ``git show``; a suffixed one fails a strict 40-hex check. Dirtiness is not
    lost — :func:`commit_hash` still reports it, and the sealed step-zero record
    carries that form, so provenance survives while the identity stays parseable.
    """
    return commit_hash(repo).removesuffix("-dirty")


@lru_cache(maxsize=4)
def describe(repo: str | None = None) -> dict:
    """Commit, branch and nearest tag — the provenance block for the report."""
    cwd = Path(repo) if repo else None
    return {
        "commit": commit_hash(repo),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd) or UNKNOWN,
        "tag": _git("describe", "--tags", "--always", cwd=cwd) or UNKNOWN,
    }
