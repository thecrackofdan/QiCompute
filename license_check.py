from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LicenseCheck:
    name: str
    status: str
    details: str


def run_license_checks() -> list[LicenseCheck]:
    checks = [
        _license_exists(),
        _license_mentions_mit(),
        _docs_reference_license(),
    ]
    return checks


def _license_exists() -> LicenseCheck:
    exists = Path("LICENSE").exists()
    return LicenseCheck("LICENSE exists", "PASS" if exists else "FAIL", "LICENSE file present" if exists else "LICENSE file missing")


def _license_mentions_mit() -> LicenseCheck:
    if not Path("LICENSE").exists():
        return LicenseCheck("license type", "FAIL", "LICENSE file missing")
    text = Path("LICENSE").read_text(encoding="utf-8")
    ok = "MIT License" in text
    return LicenseCheck("license type", "PASS" if ok else "WARN", "MIT License detected" if ok else "license type not recognized")


def _docs_reference_license() -> LicenseCheck:
    docs = ["README.md", "PROJECT_INFO.md"]
    missing = [doc for doc in docs if Path(doc).exists() and "license" not in Path(doc).read_text(encoding="utf-8").lower()]
    return LicenseCheck("docs mention licensing", "PASS" if not missing else "WARN", f"missing={','.join(missing)}" if missing else "docs reference licensing")


def main() -> int:
    checks = run_license_checks()
    for check in checks:
        print(f"{check.status} {check.name}: {check.details}")
    return 0 if all(check.status != "FAIL" for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
