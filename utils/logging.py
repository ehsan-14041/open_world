"""Thin logging wrapper with timestamps; redacts API keys in debug."""

import logging
import re
import sys
from datetime import datetime


def _redact_keys(msg: str) -> str:
    """Redact API key-like substrings for safe logging."""
    if not msg:
        return msg
    # Mask patterns like key="sk-xxx" or api_key: sk-xxx
    msg = re.sub(r'(api_key|apikey|password)\s*[:=]\s*["\']?[^"\'}\s]{8,}', r'\1=***', msg, flags=re.I)
    return msg


def get_logger(name: str, level: int = logging.INFO, debug_redact: bool = True) -> logging.Logger:
    """Return a logger that prints with timestamps; in DEBUG, redact keys."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    if debug_redact and level == logging.DEBUG:
        # Wrap handler to redact
        for h in logger.handlers:
            if not getattr(h, "_redact_filter", False):
                orig_emit = h.emit
                def emit(record):
                    record.msg = _redact_keys(str(record.msg))
                    record.args = ()
                    orig_emit(record)
                h.emit = emit
                h._redact_filter = True
    return logger
