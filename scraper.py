"""兼容旧入口：python scraper.py → 转发到新流水线。"""

from main import main

if __name__ == "__main__":
    raise SystemExit(main())
