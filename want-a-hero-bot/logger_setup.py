"""
Logging configuration for the Want-A-Hero bot.

Produces two outputs:
  1. Rotating file handler  →  logs/wantahero.log
  2. Console (stdout) handler  →  visible in systemd journalctl

Log format:
  2026-05-18 14:32:01 UTC | INFO  | [JamesTheGreat#1234] /wantahero — ...
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

import config


def setup_logger(name: str = "wantahero") -> logging.Logger:
    """Configure and return the root bot logger."""
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called more than once
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s UTC | %(levelname)-5s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Make the UTC marker accurate by forcing UTC time
    formatter.converter = lambda *_: __import__("time").gmtime()

    # ── Rotating file handler ─────────────────────────────────────────────────
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "wantahero.log"

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
