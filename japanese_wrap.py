#!/usr/bin/env python3
"""Wrap Japanese text near a target length with natural break positions."""

from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from typing import Optional

try:
    from sudachipy import dictionary
    from sudachipy import tokenizer as sudachi_tokenizer
except ImportError:
    dictionary = None
    sudachi_tokenizer = None


STRONG_AFTER = set("。．！？!?；;：:")
WEAK_AFTER = set("、，,")
OPENING = set("「『（([{【〈《")
CLOSING = set("」』）)]}】〉》")
NO_LINE_START = set("、。，．！？!?；;：:」』）)]}】〉》ぁぃぅぇぉっゃゅょァィゥェォッャュョー")
NO_LINE_END = OPENING
SINGLE_PARTICLES = set("はがをにへでともやか")
LINE_START_PARTICLES = set("はがをにへでとのもやかねよぞ")
PARTICLE_RE = re.compile(
    r"(?:から|まで|より|ほど|だけ|しか|など|なら|ので|のに|ても|でも|って|とは|には|では|へは|には|は|が|を|に|へ|で|と|も|や|か|ね|よ|ぞ)$"
)
NO_SPLIT_PAIRS = {
    "でき",
    "です",
    "でし",
    "では",
    "でも",
    "であ",
    "ます",
    "まし",
    "ませ",
    "たい",
    "きる",
    "する",
    "れる",
    "られ",
    "せる",
    "ない",
    "なら",
    "から",
    "より",
    "ので",
    "のに",
    "には",
    "では",
    "につ",
    "にく",
    "ごと",
    "み返",
    "み手",
    "り返",
    "ため",
    "こと",
    "もの",
    "かな",
    "やす",
    "とし",
    "とき",
}
NO_LINE_START_WORDS = (
    "ない",
    "ます",
    "ました",
    "ません",
    "いて",
    "いた",
    "いる",
    "った",
    "って",
    "さ",
    "み",
)
SUDACHI_MODES = {
    "A": "short",
    "B": "middle",
    "C": "long",
}
SUDACHI_TOKENIZER = None


def get_sudachi_tokenizer():
    global SUDACHI_TOKENIZER
    if dictionary is None:
        return None
    if SUDACHI_TOKENIZER is None:
        SUDACHI_TOKENIZER = dictionary.Dictionary().create()
    return SUDACHI_TOKENIZER


def get_sudachi_mode(mode_name: str):
    if sudachi_tokenizer is None:
        return None
    return getattr(sudachi_tokenizer.Tokenizer.SplitMode, mode_name)


def is_kanji(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def is_hiragana(char: str) -> bool:
    return "\u3040" <= char <= "\u309f"


def is_katakana(char: str) -> bool:
    return "\u30a0" <= char <= "\u30ff"


def break_penalty(text: str, index: int) -> float:
    """Return the penalty for breaking after text[index - 1]."""
    prev = text[index - 1] if index > 0 else ""
    nxt = text[index] if index < len(text) else ""
    before = text[max(0, index - 4) : index]

    if prev in NO_LINE_END or nxt in NO_LINE_START:
        return math.inf
    if nxt in LINE_START_PARTICLES:
        return math.inf
    if prev + nxt in NO_SPLIT_PAIRS:
        return math.inf
    if prev.isascii() and nxt.isascii() and (prev.isalnum() or nxt.isalnum()):
        return math.inf
    if is_kanji(prev) and is_hiragana(nxt):
        return math.inf
    if is_hiragana(prev) and is_hiragana(nxt) and prev not in SINGLE_PARTICLES:
        return math.inf
    if is_hiragana(prev) and any(text.startswith(word, index) for word in NO_LINE_START_WORDS):
        return math.inf
    if (is_kanji(prev) and is_kanji(nxt)) or (is_katakana(prev) and is_katakana(nxt)):
        return math.inf
    if prev.isspace() or nxt.isspace():
        return 0
    if prev in STRONG_AFTER:
        return 0
    if prev in WEAK_AFTER:
        return 2
    if prev in CLOSING:
        return 3
    if nxt in OPENING:
        return 4
    if PARTICLE_RE.search(before):
        return 8
    return 20


def sudachi_break_penalties(text: str, mode_name: str) -> Optional[dict[int, float]]:
    tokenizer = get_sudachi_tokenizer()
    mode = get_sudachi_mode(mode_name)
    if tokenizer is None or mode is None:
        return None

    penalties = {}
    pos = 0
    morphemes = list(tokenizer.tokenize(text, mode))
    for i, morpheme in enumerate(morphemes):
        surface = morpheme.surface()
        pos += len(surface)
        if pos >= len(text):
            continue

        pos_info = morpheme.part_of_speech()
        pos0 = pos_info[0]
        pos1 = pos_info[1] if len(pos_info) > 1 else ""
        prev = text[pos - 1]
        nxt = text[pos]

        if break_penalty(text, pos) == math.inf:
            continue
        if pos0 == "補助記号" or prev in STRONG_AFTER:
            penalties[pos] = 0
        elif prev in WEAK_AFTER:
            penalties[pos] = 2
        elif pos0 == "助詞":
            penalties[pos] = 4
        elif pos0 == "助動詞":
            penalties[pos] = 10
        elif pos0 == "接尾辞":
            penalties[pos] = 14
        elif nxt in OPENING:
            penalties[pos] = 6
        elif pos0 == "名詞" and pos1 in {"普通名詞", "固有名詞"}:
            penalties[pos] = 24
        else:
            penalties[pos] = 18

        if i + 1 < len(morphemes):
            next_pos_info = morphemes[i + 1].part_of_speech()
            if next_pos_info[0] in {"助詞", "助動詞", "接尾辞"}:
                penalties[pos] += 18

    return penalties


def choose_break_penalties(text: str, engine: str, sudachi_mode: str) -> Optional[dict[int, float]]:
    if engine == "rule":
        return None

    penalties = sudachi_break_penalties(text, sudachi_mode)
    if penalties is not None:
        return penalties
    if engine == "sudachi":
        raise RuntimeError(
            "SudachiPy is not installed. Install it with: "
            "python -m pip install sudachipy sudachidict_core"
        )
    return None


def boundary_penalty(
    text: str,
    index: int,
    penalties: Optional[dict[int, float]],
) -> float:
    if index >= len(text):
        return 0
    if penalties is not None:
        return penalties.get(index, math.inf)
    return break_penalty(text, index)


def split_long_text(text: str, max_bytes: int = 40000) -> list[str]:
    chunks = []
    start = 0
    last_break = None
    for index, char in enumerate(text):
        if char in STRONG_AFTER:
            last_break = index + 1
        if len(text[start : index + 1].encode("utf-8")) <= max_bytes:
            continue

        split_at = last_break if last_break and last_break > start else index
        chunks.append(text[start:split_at].strip())
        start = split_at
        last_break = None

    tail = text[start:].strip()
    if tail:
        chunks.append(tail)
    return [chunk for chunk in chunks if chunk]


def char_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in {"F", "W", "A"}:
        return 2
    return 1


def width_prefixes(text: str) -> list[int]:
    widths = [0]
    for char in text:
        widths.append(widths[-1] + char_width(char))
    return widths


def text_width(text: str) -> int:
    return sum(char_width(char) for char in text)


def polish_lines(
    lines: list[str],
    target: int,
    min_width: int,
    engine: str,
    sudachi_mode: str,
    passes: int = 3,
) -> list[str]:
    if len(lines) < 2:
        return lines

    polished = lines[:]
    for _ in range(passes):
        changed = False
        for index in range(len(polished) - 1):
            current = polished[index]
            following = polished[index + 1]
            current_width = text_width(current)
            slack = target - current_width
            if slack <= 0:
                continue

            combined = current + following
            try:
                penalties = choose_break_penalties(combined, engine, sudachi_mode)
            except RuntimeError:
                penalties = None

            old_penalty = boundary_penalty(combined, len(current), penalties)
            best = None
            for offset in range(1, len(following)):
                prefix = following[:offset]
                prefix_width = text_width(prefix)
                if prefix_width > slack:
                    break

                remaining = following[offset:]
                if text_width(remaining) < min_width and index + 1 < len(polished) - 1:
                    continue

                new_index = len(current) + offset
                new_penalty = boundary_penalty(combined, new_index, penalties)
                if new_penalty == math.inf:
                    continue
                short_line_fill = (
                    current_width < min_width
                    and text_width(remaining) >= min_width
                    and new_penalty <= 8
                )
                if not short_line_fill and old_penalty - new_penalty < 4:
                    continue

                fill = target - current_width - prefix_width
                candidate = (new_penalty, fill, -prefix_width, offset)
                if best is None or candidate < best:
                    best = candidate

            if best is None:
                continue

            offset = best[3]
            polished[index] = current + following[:offset]
            polished[index + 1] = following[offset:]
            changed = True

        for index in range(1, len(polished)):
            current = polished[index]
            current_width = text_width(current)
            if current_width >= min_width:
                continue

            previous = polished[index - 1]
            previous_width = text_width(previous)
            combined = previous + current
            try:
                penalties = choose_break_penalties(combined, engine, sudachi_mode)
            except RuntimeError:
                penalties = None

            best = None
            for cut in range(1, len(previous)):
                suffix = previous[cut:]
                suffix_width = text_width(suffix)
                new_previous_width = previous_width - suffix_width
                new_current_width = current_width + suffix_width
                if new_previous_width < min_width:
                    continue
                if new_current_width > target:
                    continue
                if new_current_width < min_width:
                    continue

                new_penalty = boundary_penalty(combined, cut, penalties)
                if new_penalty == math.inf or new_penalty > 10:
                    continue

                candidate = (suffix_width, new_penalty, cut)
                if best is None or candidate < best:
                    best = candidate

            if best is None:
                continue

            cut = best[2]
            polished[index - 1] = previous[:cut]
            polished[index] = previous[cut:] + current
            changed = True

        if not changed:
            break
    return polished


def wrap_japanese(
    text: str,
    target: int = 86,
    min_ratio: float = 0.86,
    engine: str = "auto",
    sudachi_mode: str = "C",
    naturalness_weight: float = 8.0,
) -> str:
    text = re.sub(r"[ \t]+", " ", text.strip())
    if not text:
        return ""
    if (engine == "sudachi" or (engine == "auto" and dictionary is not None)) and len(
        text.encode("utf-8")
    ) > 40000:
        min_width = max(1, math.ceil(target * min_ratio))
        chunk_lines = "\n".join(
            wrap_japanese(chunk, target, min_ratio, engine, sudachi_mode, naturalness_weight)
            for chunk in split_long_text(text)
        ).splitlines()
        chunk_lines = polish_lines(
            [line for line in chunk_lines if line],
            target,
            min_width,
            engine,
            sudachi_mode,
        )
        return "\n".join(chunk_lines)

    n = len(text)
    widths = width_prefixes(text)
    min_width = max(1, math.ceil(target * min_ratio))
    max_width = target
    morph_penalties = choose_break_penalties(text, engine, sudachi_mode)

    cost = [math.inf] * (n + 1)
    prev = [-1] * (n + 1)
    cost[0] = 0

    for end in range(1, n + 1):
        for start in range(end - 1, -1, -1):
            line_width = widths[end] - widths[start]
            if line_width > max_width:
                break
            if cost[start] == math.inf:
                continue

            if start != 0 and line_width < min_width and end != n:
                continue

            if end == n:
                naturalness = 0
            elif morph_penalties is not None:
                naturalness = morph_penalties.get(end, math.inf)
            else:
                naturalness = break_penalty(text, end)
            if naturalness == math.inf:
                continue

            raggedness = (line_width - target) ** 2
            candidate_cost = cost[start] + raggedness + naturalness * naturalness_weight

            if candidate_cost < cost[end]:
                cost[end] = candidate_cost
                prev[end] = start

    if prev[n] == -1:
        return greedy_wrap(text, target, morph_penalties)

    lines = []
    pos = n
    while pos > 0:
        start = prev[pos]
        lines.append(text[start:pos].strip())
        pos = start

    lines = list(reversed(lines))
    lines = polish_lines(lines, target, min_width, engine, sudachi_mode)
    return "\n".join(lines)


def greedy_wrap(text: str, target: int, break_penalties: Optional[dict[int, float]] = None) -> str:
    lines = []
    pos = 0
    while pos < len(text):
        width = 0
        hard_limit = pos
        while hard_limit < len(text) and width + char_width(text[hard_limit]) <= target:
            width += char_width(text[hard_limit])
            hard_limit += 1

        best = hard_limit
        for i in range(hard_limit, pos, -1):
            penalty = break_penalties.get(i, math.inf) if break_penalties is not None else break_penalty(text, i)
            if penalty <= 8:
                best = i
                break

        if best == pos:
            best = max(pos + 1, hard_limit)

        lines.append(text[pos:best].strip())
        pos = best
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Japanese line wrapper that balances natural breaks and line length."
    )
    parser.add_argument(
        "-n",
        "--target",
        type=int,
        default=86,
        help="target display width per line; ASCII is 1, Japanese full-width text is 2",
    )
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=0.86,
        help="minimum line length as a ratio of target, except the final line",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "sudachi", "rule"),
        default="auto",
        help="line-break engine: auto uses SudachiPy when installed, rule uses built-in rules",
    )
    parser.add_argument(
        "--sudachi-mode",
        choices=tuple(SUDACHI_MODES),
        default="C",
        help="Sudachi split mode: A=short, B=middle, C=long",
    )
    parser.add_argument(
        "--naturalness-weight",
        type=float,
        default=8.0,
        help="how strongly natural break positions are preferred over line-width evenness",
    )
    parser.add_argument("-o", "--output", help="output text file; stdout is used when omitted")
    parser.add_argument("file", nargs="?", help="input text file; stdin is used when omitted")
    args = parser.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    try:
        wrapped = []
        for source_line in text.splitlines():
            if not source_line.strip():
                wrapped.append("")
                continue
            wrapped.append(
                wrap_japanese(
                    source_line,
                    args.target,
                    args.min_ratio,
                    args.engine,
                    args.sudachi_mode,
                    args.naturalness_weight,
                )
            )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    output = "\n".join(wrapped)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
