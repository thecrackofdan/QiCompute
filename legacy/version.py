from __future__ import annotations

from pathlib import Path


def current_version() -> str:
    return Path("VERSION").read_text(encoding="utf-8").strip()


def main() -> int:
    print(f"QiCompute {current_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
