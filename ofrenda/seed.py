"""Copy the fictional sample altar into the data directory on first run."""

from __future__ import annotations

import shutil

from ofrenda.config import Settings


def ensure_seed(settings: Settings) -> None:
    settings.portrait_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    sample_tree = settings.sample_dir / "family.json"
    if not settings.tree_path.exists() and sample_tree.is_file():
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(sample_tree, settings.tree_path)
    sample_portraits = settings.sample_dir / "portraits"
    if sample_portraits.is_dir():
        for source in sample_portraits.glob("*.png"):
            dest = settings.portrait_dir / source.name
            if not dest.exists():
                shutil.copy(source, dest)


def reset_to_sample(settings: Settings) -> None:
    """Replace the working altar with the fictional sample. Local edits are cleared."""
    if settings.tree_path.exists():
        settings.tree_path.unlink()
    if settings.portrait_dir.exists():
        shutil.rmtree(settings.portrait_dir)
    if settings.cache_dir.exists():
        shutil.rmtree(settings.cache_dir)
    ensure_seed(settings)
