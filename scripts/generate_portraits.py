"""Regenerate the fictional sample portraits. Safe to run again."""

from pathlib import Path

from ofrenda.portraits import write_portraits

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    paths = write_portraits(ROOT / "sample" / "portraits")
    for path in paths:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
