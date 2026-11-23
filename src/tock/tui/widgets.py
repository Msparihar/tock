"""Big seven-segment style digits drawn with block characters."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

# 5 x 7 pixel glyphs. Each pixel is drawn as two block characters, which is
# close to square in a terminal cell.
_FONT = {
    "0": ["#####", "#...#", "#...#", "#...#", "#...#", "#...#", "#####"],
    "1": ["....#", "....#", "....#", "....#", "....#", "....#", "....#"],
    "2": ["#####", "....#", "....#", "#####", "#....", "#....", "#####"],
    "3": ["#####", "....#", "....#", "#####", "....#", "....#", "#####"],
    "4": ["#...#", "#...#", "#...#", "#####", "....#", "....#", "....#"],
    "5": ["#####", "#....", "#....", "#####", "....#", "....#", "#####"],
    "6": ["#####", "#....", "#....", "#####", "#...#", "#...#", "#####"],
    "7": ["#####", "....#", "....#", "....#", "....#", "....#", "....#"],
    "8": ["#####", "#...#", "#...#", "#####", "#...#", "#...#", "#####"],
    "9": ["#####", "#...#", "#...#", "#####", "....#", "....#", "#####"],
    ":": [".", ".", "#", ".", "#", ".", "."],
    ".": [".", ".", ".", ".", ".", ".", "#"],
    " ": [".", ".", ".", ".", ".", ".", "."],  # a colon in its "off" blink
}
HEIGHT = 7
PIXEL = "██"
BLANK = "  "


def render_big(text: str, styles: list[str] | None = None) -> Text:
    """Draw `text` in the big font. `styles` gives one Rich style per character."""
    styles = styles or [""] * len(text)
    out = Text(no_wrap=True, overflow="crop")
    for row in range(HEIGHT):
        for i, ch in enumerate(text):
            glyph = _FONT.get(ch, _FONT[" "])
            line = "".join(PIXEL if px == "#" else BLANK for px in glyph[row])
            out.append(line, style=styles[i])
            if i < len(text) - 1:
                out.append(" ")
        if row < HEIGHT - 1:
            out.append("\n")
    return out


def big_width(text: str) -> int:
    return sum(len(_FONT.get(c, _FONT[" "])[0]) * 2 for c in text) + max(0, len(text) - 1)


class BigDigits(Widget):
    """Shows `value` in big digits. Characters after `dim_from` are drawn dimmer."""

    DEFAULT_CSS = """
    BigDigits { width: auto; height: 7; }
    """

    value: reactive[str] = reactive("00:00", layout=True)
    dim_from: reactive[int] = reactive(-1)

    def __init__(self, value: str = "00:00", *, dim_from: int = -1, **kwargs):
        super().__init__(**kwargs)
        self.set_reactive(BigDigits.value, value)
        self.set_reactive(BigDigits.dim_from, dim_from)

    def get_content_width(self, container, viewport) -> int:
        return big_width(self.value)

    def get_content_height(self, container, viewport, width) -> int:
        return HEIGHT

    def render(self) -> Text:
        # Colour comes from CSS (`color:`); the tail after `dim_from` (seconds) is dimmed.
        styles = ["dim" if 0 <= self.dim_from <= i else "" for i in range(len(self.value))]
        return render_big(self.value, styles)
