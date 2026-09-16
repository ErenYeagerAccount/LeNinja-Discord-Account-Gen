"""Terminal presentation. Run this module directly for a UI-only preview."""

import os
import shutil
import sys
import textwrap


SERVICES = (
    ("C", "Cybertemp"), ("H", "Hotmail"), ("Z", "Zeus-X"),
    ("A", "Afham"), ("D", "DuckMail"), ("R", "CrowMail"),
)
LOGO = (
    "██╗     ███████╗███╗   ██╗██╗███╗   ██╗     ██╗ █████╗ ",
    "██║     ██╔════╝████╗  ██║██║████╗  ██║     ██║██╔══██╗",
    "██║     █████╗  ██╔██╗ ██║██║██╔██╗ ██║     ██║███████║",
    "██║     ██╔══╝  ██║╚██╗██║██║██║╚██╗██║██   ██║██╔══██║",
    "███████╗███████╗██║ ╚████║██║██║ ╚████║╚█████╔╝██║  ██║",
    "╚══════╝╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝ ╚════╝ ╚═╝  ╚═╝",
)
PALETTE = {
    "cyan": (94, 234, 242),
    "violet": (178, 145, 255),
    "text": (226, 232, 240),
    "muted": (148, 163, 184),
    "edge": (80, 99, 125),
    "green": (110, 231, 183),
    "amber": (251, 191, 100),
    "red": (251, 113, 133),
}


def supports_unicode():
    try:
        "╭╮╰╯│─██›".encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def use_color():
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.getenv("TERM") != "dumb"


def paint(text, tone, enabled):
    if not enabled:
        return text
    r, g, b = PALETTE[tone] if isinstance(tone, str) else tone
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"


def _log_layout(width=None, color=None, unicode=None):
    width = max(20, width if width is not None else shutil.get_terminal_size((80, 24)).columns)
    content_width = min(76, width - 4)
    margin = " " * max(1, (width - content_width) // 2)
    return (
        content_width, margin,
        use_color() if color is None else color,
        supports_unicode() if unicode is None else unicode,
    )


def render_activity_header(width=None, color=None, unicode=None):
    size, margin, color, unicode = _log_layout(width, color, unicode)
    rule = "─" if unicode else "-"
    title = "L E N I N J A  /  ACTIVITY" if size >= 24 else "ACTIVITY"
    return "\n" + margin + paint(title, "violet", color) + "\n" + margin + paint(rule * size, "edge", color) + "\n"


def render_log(level, message, timestamp, width=None, color=None, unicode=None):
    """Format one event; wrapping and colors affect console output only."""
    size, margin, color, unicode = _log_layout(width, color, unicode)
    level = str(level).upper()
    tone = {
        "SUCCESS": "green", "WARNING": "amber", "ERROR": "red",
        "INFO": "cyan", "DEBUG": "muted", "INPUT": "violet",
    }.get(level, "muted")
    badge = f"[{level}]"
    separator = "│" if unicode else "|"
    time_label = str(timestamp)
    plain_prefix = f"{time_label}  {separator}  {badge:<9}  "
    prefix = (
        paint(time_label, "muted", color)
        + paint(f"  {separator}  ", "edge", color)
        + paint(f"{badge:<9}", tone, color) + "  "
    )
    message = str(message)
    message = message[:1].upper() + message[1:]
    # Stack metadata above the message when columns would be too cramped.
    if size - len(plain_prefix) < 18:
        metadata = textwrap.wrap(f"{time_label} {badge}", width=size)
        lines = [margin + paint(row, tone, color) for row in metadata]
        indent = "  "
        for paragraph in message.splitlines() or [""]:
            for row in textwrap.wrap(paragraph, width=size - 2) or [""]:
                lines.append(margin + indent + paint(row, "text", color))
        return "\n".join(lines)
    rows = []
    for paragraph in message.splitlines() or [""]:
        rows.extend(textwrap.wrap(paragraph, width=size - len(plain_prefix)) or [""])
    continuation = " " * (len(time_label) + 2) + separator + " " * (len(plain_prefix) - len(time_label) - 3)
    return "\n".join(
        margin + (prefix if index == 0 else paint(continuation, "edge", color))
        + paint(row, "text", color)
        for index, row in enumerate(rows)
    )


def render_summary(valid, locked, attempted, elapsed, width=None, color=None, unicode=None):
    size, margin, color, unicode = _log_layout(width, color, unicode)
    tl, tr, bl, br, vertical, rule = ("╭", "╮", "╰", "╯", "│", "─") if unicode else ("+", "+", "+", "+", "|", "-")
    title = " SESSION SUMMARY " if size >= 24 else " SUMMARY "
    inner = size - 2
    lines = ["", margin + paint(tl + rule + title + rule * (inner - len(title) - 1) + tr, "edge", color)]

    def row(content):
        lines.append(margin + paint(vertical, "edge", color) + content + paint(vertical, "edge", color))

    metrics = (
        ("VALID", str(valid), "green"),
        ("LOCKED", str(locked), "amber"),
        ("ATTEMPTED", str(attempted), "cyan"),
        ("ELAPSED", f"{elapsed:.1f}s", "violet"),
    )
    row(" " * inner)
    cell = inner // 4
    if size >= 60 and all(max(len(label), len(value)) <= cell - 2 for label, value, _ in metrics):
        padding = " " * (inner - cell * 4)
        row("".join(paint(label.center(cell), "muted", color) for label, _, _ in metrics) + padding)
        row("".join(paint(value.center(cell), tone, color) for _, value, tone in metrics) + padding)
    else:
        for label, value, tone in metrics:
            for part in textwrap.wrap(f"{label}: {value}", width=inner - 2):
                row(paint(" " + part.ljust(inner - 2) + " ", tone, color))
    row(" " * inner)
    lines.append(margin + paint(bl + rule * inner + br, "edge", color))
    return "\n".join(lines)


def render_interface(width=None, color=None, unicode=None):
    """Return a responsive menu without reading input or starting the app."""
    width = max(20, width if width is not None else shutil.get_terminal_size((80, 24)).columns)
    color = use_color() if color is None else color
    unicode = supports_unicode() if unicode is None else unicode
    content_width = min(76, width - 4)
    margin = " " * max(1, (width - content_width) // 2)
    tl, tr, bl, br, vertical, horizontal = ("╭", "╮", "╰", "╯", "│", "─") if unicode else ("+", "+", "+", "+", "|", "-")
    lines = [""]

    def line(text="", tone="text"):
        lines.append(margin + paint(text, tone, color))

    large_logo = unicode and content_width >= max(map(len, LOGO))
    line("CONSOLE / HOME" if large_logo else "L E N I N J A", "cyan")
    line(horizontal * content_width, "edge")
    line()
    if large_logo:
        for index, row in enumerate(LOGO):
            ratio = index / (len(LOGO) - 1)
            start, end = PALETTE["cyan"], PALETTE["violet"]
            tone = tuple(round(a + (b - a) * ratio) for a, b in zip(start, end))
            line(row.center(content_width), tone)
        line()
    for subtitle in textwrap.wrap("Account automation console", width=content_width):
        line(subtitle.center(content_width), "muted")
    line()
    line("01 / SERVICE", "violet")
    line("Select your email provider" if content_width >= 26 else "Select provider", "text")
    line()

    columns = 2 if content_width >= 58 else 1
    gap = "  "
    card_width = (content_width - (columns - 1) * len(gap)) // columns
    for offset in range(0, len(SERVICES), columns):
        cards = []
        for key, name in SERVICES[offset:offset + columns]:
            label = f" [{key}] {name}"
            middle = (
                paint(vertical, "edge", color)
                + paint(f" [{key}]", "cyan", color)
                + paint(f" {name}" + " " * (card_width - 2 - len(label)), "text", color)
                + paint(vertical, "edge", color)
            )
            cards.append((
                paint(tl + horizontal * (card_width - 2) + tr, "edge", color),
                middle,
                paint(bl + horizontal * (card_width - 2) + br, "edge", color),
            ))
        for row in zip(*cards):
            lines.append(margin + gap.join(row))
    line()
    if content_width >= 44:
        line("Type a letter to select  /  Enter: Cybertemp", "muted")
    else:
        line("Type a letter", "muted")
        line("Enter: Cybertemp", "muted")
    line(horizontal * content_width, "edge")
    return "\n".join(lines)


def format_prompt(query):
    color = use_color()
    marker = "›" if supports_unicode() else ">"
    width = max(20, shutil.get_terminal_size((80, 24)).columns)
    margin = " " * max(1, (width - min(76, width - 4)) // 2)
    return "\n" + margin + paint(marker, "cyan", color) + " " + paint(query.strip(), "text", color) + " "


def run_preview():
    """Preview service selection locally, without importing the application."""
    print(render_interface())
    print("\n  UI preview only. Select a service to preview the confirmation.")
    services = dict(SERVICES)
    while True:
        try:
            choice = input(format_prompt("Service:")).strip().upper() or "C"
        except (EOFError, KeyboardInterrupt):
            print("\n  Preview closed.")
            return
        if choice not in services:
            print("  Choose C, H, Z, A, D or R; press Enter for Cybertemp.")
            continue
        print(paint(f"\n  Selected: {services[choice]} [{choice}]", "cyan", use_color()))
        print("  Preview complete. No account actions were started.")
        return


def run_log_preview():
    """Print sample events without importing or running the application."""
    print(render_activity_header())
    samples = (
        ("21:11:36", "SUCCESS", "Configuration loaded"),
        ("21:11:43", "INFO", "Connecting to service..."),
        ("21:12:17", "INFO", "Waiting for verification email..."),
        ("21:12:41", "INFO", "Opening verification link..."),
        ("21:12:44", "WARNING", "Verification pending; waiting for the next response."),
        ("21:13:18", "SUCCESS", "Verified successfully"),
        ("21:13:22", "DEBUG", "Example of a longer diagnostic message that wraps beneath the event text while keeping timestamps and status labels aligned."),
        ("21:13:23", "ERROR", "Example error: service unavailable"),
    )
    for timestamp, level, message in samples:
        print(render_log(level, message, timestamp))
    print(render_summary(1, 0, 1, 104.8))
    print("\n  Sample logs only. No account actions were started.")


if __name__ == "__main__":
    # Enable ANSI support on older Windows consoles when available.
    try:
        from colorama import just_fix_windows_console
        just_fix_windows_console()
    except ImportError:
        pass
    if "--logs" in sys.argv[1:]:
        run_log_preview()
    else:
        run_preview()
