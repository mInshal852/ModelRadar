"""Validate files under config/. Requires PyYAML (pip install pyyaml)."""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TOP_LEVEL = 17


def validate_categories(path: Path) -> list[str]:
    errors: list[str] = []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    top = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(top, list):
        return [f"{path.name}: expected a top-level 'categories' list"]

    if len(top) != EXPECTED_TOP_LEVEL:
        errors.append(f"{path.name}: expected {EXPECTED_TOP_LEVEL} top-level categories, got {len(top)}")

    seen: set[str] = set()

    def check(node: dict[str, object], where: str) -> None:
        slug, name = node.get("slug"), node.get("name")
        if not isinstance(slug, str) or not isinstance(name, str) or not slug or not name:
            errors.append(f"{where}: every category needs a non-empty slug and name")
            return
        if slug in seen:
            errors.append(f"{where}: duplicate slug '{slug}'")
        seen.add(slug)

    for parent in top:
        check(parent, "top-level")
        for child in parent.get("children", []):
            check(child, f"child of '{parent.get('slug')}'")
    return errors


def main() -> int:
    errors = validate_categories(ROOT / "config" / "categories.yaml")
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("config OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
