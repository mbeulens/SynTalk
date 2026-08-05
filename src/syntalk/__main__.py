"""Console entry point."""

from __future__ import annotations

import sys


def main() -> int:
    from .gui import SynTalkApp

    return SynTalkApp().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
