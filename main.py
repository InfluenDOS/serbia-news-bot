#!/usr/bin/env python3
"""入口：python main.py"""

from __future__ import annotations

import logging
import sys

from serbia_news_bot.pipeline import run_pipeline


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        path = run_pipeline()
    except Exception as exc:  # noqa: BLE001
        logging.exception("流水线失败: %s", exc)
        return 1
    print(f"Report written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
