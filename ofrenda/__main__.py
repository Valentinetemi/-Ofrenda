"""python -m ofrenda"""

from __future__ import annotations

import logging

import uvicorn

from ofrenda.config import get_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    uvicorn.run(
        "ofrenda.app:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
