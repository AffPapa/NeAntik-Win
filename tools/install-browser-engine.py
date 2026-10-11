"""Offline verified provisioning; does not download or modify an existing engine."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from browser_engine import EngineError, install_verified_archive

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(install_verified_archive(args.portable_root, args.archive))
    except (EngineError, OSError) as exc:
        print(f"Native engine provisioning failed: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
