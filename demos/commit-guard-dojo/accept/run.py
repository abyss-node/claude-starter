import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]
import acceptkit as ak  # noqa: E402
import checks  # noqa: E402

ak.main(checks.TESTS)
