"""Open the profile form with disposable data for manual visual QA.

The native capability is mocked for layout review only. This script does not
launch a browser or read the user's portable Data directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nevision_win as nv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=("light", "dark"), default="dark")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="neantik-visual-qa-") as temporary:
        paths = nv.AppPaths(Path(temporary))
        storage = nv.Storage(paths)
        storage.save_profile({"name": "Example QA profile", "group_name": "QA"})
        app = nv.NeVisionApp(storage, paths)
        app.set_theme_preference(args.theme)
        with patch.object(app.launcher, "native_persona_capabilities", return_value={"stable_seed": True}):
            nv.ProfileDialog(app)
            app.run()


if __name__ == "__main__":
    main()
