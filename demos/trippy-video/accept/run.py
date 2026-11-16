"""The held-out checks of trippy-video: demos/check.py starts this as
`<python> -I -S -B -X utf8 accept/run.py` with DEMO_WORKSPACE naming a copy of the workspace.
Each check prints one result line (demos/acceptkit.py); the checks are in test_trippy.py."""
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]
import acceptkit as ak  # noqa: E402
import test_trippy  # noqa: E402

ak.main(test_trippy.TESTS)
