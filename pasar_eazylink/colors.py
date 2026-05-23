import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


def enabled() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.getenv("NO_COLOR") is not None:
        return False
    term = os.getenv("TERM", "").strip().lower()
    return term not in {"", "dumb"}


def style(text: str, *codes: str) -> str:
    if not enabled() or not codes:
        return text
    return f"{''.join(codes)}{text}{RESET}"


def title(text: str) -> str:
    return style(text, BOLD, CYAN)


def success(text: str) -> str:
    return style(text, GREEN)


def warning(text: str) -> str:
    return style(text, YELLOW)


def error(text: str) -> str:
    return style(text, RED)
