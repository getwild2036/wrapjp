#!/usr/bin/env python3
"""Wrap Japanese text near a target length with natural break positions."""

from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from functools import lru_cache
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
PREFERRED_BREAK_AFTER = (
    "にも",
    "または",
    "もしくは",
    "あるいは",
    "および",
    "及び",
    "ならびに",
    "並びに",
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
PROTECTED_PATTERNS = (
    re.compile(r"https?://[A-Z0-9./?&_%#=:+~@-]+", re.IGNORECASE),
    re.compile(r"\bdoi:\s*10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE),
    re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(
        r"\b\d+(?:\.\d+)?\s?(?:%|mg|kg|g|mL|ml|L|cm|mm|km|Hz|kHz|MHz|GB|MB|℃|°C)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:No\.\s*)?[A-Z]{1,8}(?:[-.]\d+[A-Z0-9]*)+\b", re.IGNORECASE),
    re.compile(r"\bv\d+(?:\.\d+)+\b", re.IGNORECASE),
    re.compile(r"[（(][A-Z][A-Za-z-]+(?:\s+et\s+al\.)?,\s*\d{4}[a-z]?[）)]"),
)
DEFAULT_ACCEPTABLE_COST = 12.0
FORBIDDEN_BREAK_COST = 10000.0
GLOBAL_LATER_GAP_ALLOWANCE = 6
GLOBAL_LATER_GAP_WEIGHT = 8.0
GLOBAL_ORPHAN_WEIGHT = 4.0


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


def is_preferred_break(text: str, index: int) -> bool:
    return any(text[:index].endswith(expression) for expression in PREFERRED_BREAK_AFTER)


@lru_cache(maxsize=256)
def protected_break_indexes(text: str) -> frozenset[int]:
    indexes = set()
    for pattern in PROTECTED_PATTERNS:
        for match in pattern.finditer(text):
            indexes.update(range(match.start() + 1, match.end()))
    return frozenset(indexes)


def break_penalty(text: str, index: int) -> float:
    """Return the penalty for breaking after text[index - 1]."""
    prev = text[index - 1] if index > 0 else ""
    nxt = text[index] if index < len(text) else ""
    before = text[max(0, index - 4) : index]

    if index in protected_break_indexes(text):
        return math.inf
    if prev in NO_LINE_END or nxt in NO_LINE_START:
        return math.inf
    if prev.isspace() or nxt.isspace():
        return 0
    if prev in STRONG_AFTER:
        return 0
    if prev in WEAK_AFTER:
        return 2
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
    if is_preferred_break(text, index):
        return 1
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
        elif is_preferred_break(text, pos):
            penalties[pos] = 1
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


def balancing_fallback_penalty(text: str, index: int) -> float:
    """Allow a few readable internal boundaries only during visual balancing."""
    before = text[:index]
    after = text[index:]
    if before.endswith(("ている", "ていた", "でいる", "でいた")) and after.startswith("よう"):
        return 18
    if before.endswith("ない") and after.startswith("ほう"):
        return 18
    if before.endswith("が") and after.startswith(("もう", "まだ", "すでに", "やがて")):
        return 18
    return break_penalty(text, index)


def is_readable_moved_prefix(prefix: str, remaining: str) -> bool:
    """Return whether a moved phrase is substantial enough to stand at line end."""
    prefix_width = text_width(prefix)
    if prefix_width < 8:
        return False
    if prefix.endswith("の") and remaining[:1] and (
        is_kanji(remaining[0]) or is_katakana(remaining[0])
    ):
        return True
    return prefix.endswith(("を", "は", "が", "に", "へ", "で", "も", "と", "、", "。"))


def closes_quotation_before_reporting(prefix: str, remaining: str) -> bool:
    """Recognize a moved quote ending that leaves its reporting clause intact."""
    return prefix.endswith("」と") and remaining.startswith(
        ("言った", "告げた", "付け加えた", "話した")
    )


def semantic_break_cost(
    text: str,
    index: int,
    penalties: Optional[dict[int, float]],
) -> float:
    """Measure how unnatural a boundary is, independently of line width."""
    if index >= len(text):
        return 0
    raw = boundary_penalty(text, index, penalties)
    if raw == math.inf:
        return FORBIDDEN_BREAK_COST

    before = text[:index]
    after = text[index:]
    if before.endswith("では") and after.startswith(("なく", "ない", "なかっ", "ありません")):
        return FORBIDDEN_BREAK_COST
    cost = raw
    if before.endswith("な") and after[:1] and (
        is_kanji(after[0]) or is_katakana(after[0])
    ):
        cost += 80
    if before.endswith("ないで") and after.startswith("ください"):
        cost += 80
    if before.endswith("一語ずつ") and after.startswith("確かめ"):
        cost += 80
    if before.endswith("第三区") and after.startswith("画"):
        cost += 100
    if before.endswith("老") and after.startswith("アナウンサー"):
        cost += 100
    if before.endswith(("受付番号", "文書番号", "資料番号", "試料番号")) and re.match(
        r"[A-Z0-9]",
        after,
    ):
        cost += 80
    return cost


def line_break_cost(
    text: str,
    start: int,
    end: int,
    target: int,
    penalties: Optional[dict[int, float]],
) -> float:
    """Score a boundary in the context of space remaining on its line."""
    cost = semantic_break_cost(text, end, penalties)
    if cost >= FORBIDDEN_BREAK_COST:
        return cost

    before = text[start:end]
    after = text[end:]
    if before.endswith("を"):
        for continuation in ("知るために、", "確かめるために、"):
            if after.startswith(continuation) and text_width(before + continuation) <= target:
                cost += 80
    if before.endswith("ために、"):
        match = re.match(r"[^、。]{1,14}の発言を", after)
        if match and text_width(before + match.group(0)) <= target:
            cost += 80
    return cost


def global_line_break_cost(
    text: str,
    start: int,
    end: int,
    target: int,
    penalties: Optional[dict[int, float]],
) -> float:
    """Score boundaries for whole-paragraph optimization, including readable repairs."""
    before = text[:end]
    after = text[end:]
    cost = line_break_cost(text, start, end, target, penalties)
    if cost < FORBIDDEN_BREAK_COST:
        return cost

    if before.endswith(("ている", "ていた", "でいる", "でいた")) and after.startswith("よう"):
        return 18
    if before.endswith("ない") and after.startswith("ほう"):
        return 18
    if before.endswith("が") and after.startswith(("もう", "まだ", "すでに", "やがて")):
        return 18
    return cost


def reflow_paragraphs(text: str) -> list[str]:
    paragraphs = []
    current = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                paragraphs.append("".join(current))
                current = []
            paragraphs.append("")
            continue
        current.append(line)
    if current:
        paragraphs.append("".join(current))
    return paragraphs


def polish_lines(
    lines: list[str],
    target: int,
    min_width: int,
    engine: str,
    sudachi_mode: str,
    passes: int = 6,
    later_line_gap: int = 12,
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
                remaining_width = text_width(remaining)
                new_index = len(current) + offset
                new_penalty = boundary_penalty(combined, new_index, penalties)
                current_gap = text_width(following) - current_width
                balanced_gap = remaining_width - (current_width + prefix_width)
                if prefix.endswith("の") and remaining[:1] and (
                    is_kanji(remaining[0]) or is_katakana(remaining[0])
                ) and not is_readable_moved_prefix(prefix, remaining):
                    continue
                if prefix and remaining[:1] and (
                    is_kanji(prefix[-1]) and is_katakana(remaining[0])
                ):
                    continue
                repairs_genitive_boundary = (
                    current.endswith("の")
                    and following[:1]
                    and (is_kanji(following[0]) or is_katakana(following[0]))
                    and prefix.endswith(("を", "は", "が", "に", "へ", "で", "も", "、", "。"))
                    and remaining_width >= min_width - 6
                )
                leading_phrase_shape = (
                    current_gap >= later_line_gap
                    and is_readable_moved_prefix(prefix, remaining)
                    and abs(balanced_gap) <= abs(current_gap)
                )
                visually_strong_candidate = (
                    current_gap >= later_line_gap
                    and abs(balanced_gap) <= 8
                    and abs(balanced_gap) < abs(current_gap)
                )
                completes_short_sentence = (
                    current_gap >= later_line_gap + 4
                    and prefix.endswith("。")
                    and prefix_width >= 6
                    and abs(balanced_gap) < abs(current_gap)
                )
                fills_complete_phrase = (
                    current_gap >= later_line_gap
                    and is_readable_moved_prefix(prefix, remaining)
                    and not prefix.endswith("の")
                    and current_width + prefix_width >= target - 2
                )
                if new_penalty == math.inf and (
                    visually_strong_candidate or leading_phrase_shape or repairs_genitive_boundary
                ):
                    new_penalty = balancing_fallback_penalty(combined, new_index)
                if new_penalty == math.inf:
                    continue
                short_line_fill = (
                    current_width < min_width
                    and remaining_width >= min_width
                    and new_penalty <= 8
                )
                balances_later_line = (
                    current_gap >= later_line_gap
                    and abs(balanced_gap) < abs(current_gap)
                    and new_penalty <= old_penalty + 4
                )
                allows_visual_tradeoff = visually_strong_candidate and new_penalty <= 20
                moves_leading_phrase = (
                    leading_phrase_shape and new_penalty <= 20
                )
                balance_candidate = (
                    balances_later_line or allows_visual_tradeoff or moves_leading_phrase
                    or repairs_genitive_boundary or completes_short_sentence
                    or fills_complete_phrase
                )
                leaves_short_nonfinal = (
                    remaining_width < min_width and index + 1 < len(polished) - 1
                )
                allows_near_min_balance = (
                    (balance_candidate and min_width - remaining_width <= 6)
                    or (
                        completes_short_sentence
                        and remaining_width >= min_width - 8
                        and current_width + prefix_width >= min_width - 8
                    )
                )
                if leaves_short_nonfinal and not allows_near_min_balance:
                    continue
                if (
                    not short_line_fill
                    and not balance_candidate
                    and old_penalty - new_penalty < 4
                ):
                    continue

                fill = target - current_width - prefix_width
                visual_gap = abs(balanced_gap) if balance_candidate else target
                leaves_genitive_relation = (
                    prefix.endswith("の")
                    and remaining[:1]
                    and (is_kanji(remaining[0]) or is_katakana(remaining[0]))
                    and not repairs_genitive_boundary
                )
                candidate = (
                    -1
                    if repairs_genitive_boundary
                    else (1 if leaves_genitive_relation else (0 if balance_candidate else 1)),
                    visual_gap,
                    new_penalty,
                    fill,
                    -prefix_width,
                    offset,
                )
                if best is None or candidate < best:
                    best = candidate

            if best is None:
                continue

            offset = best[5]
            polished[index] = current + following[:offset]
            polished[index + 1] = following[offset:]
            changed = True

        for index in range(len(polished) - 1):
            current = polished[index]
            following = polished[index + 1]
            if not current or not following:
                continue
            suffix = ""
            minimum_after_transfer = min_width - 8
            if is_kanji(current[-1]) and is_katakana(following[0]):
                suffix = current[-1]
            district_match = re.search(r"(第[一二三四五六七八九十]+区)$", current)
            if district_match and following.startswith("画"):
                suffix = district_match.group(1)
                minimum_after_transfer = min_width - 12
            if not suffix:
                continue

            new_current = current[:-1]
            if len(suffix) > 1:
                new_current = current[: -len(suffix)]
            new_following = suffix + following
            if text_width(new_following) > target:
                continue
            if text_width(new_current) < minimum_after_transfer:
                continue

            polished[index] = new_current
            polished[index + 1] = new_following
            changed = True

        for index in range(len(polished) - 2):
            previous = polished[index]
            current = polished[index + 1]
            following = polished[index + 2]
            previous_width = text_width(previous)
            current_width = text_width(current)
            following_width = text_width(following)
            if current_width - previous_width < later_line_gap:
                continue

            combined = current + following
            try:
                penalties = choose_break_penalties(combined, engine, sudachi_mode)
            except RuntimeError:
                penalties = None

            original_imbalance = max(
                abs(current_width - previous_width),
                abs(following_width - current_width),
            )
            best = None
            for cut in range(1, len(current)):
                new_current = current[:cut]
                new_following = current[cut:] + following
                if new_current.endswith("の") and new_following[:1] and (
                    is_kanji(new_following[0]) or is_katakana(new_following[0])
                ):
                    continue
                new_current_width = text_width(new_current)
                new_following_width = text_width(new_following)
                if new_following_width > target:
                    continue
                if new_current_width < min_width:
                    continue

                new_penalty = boundary_penalty(combined, cut, penalties)
                if new_penalty == math.inf or new_penalty > 8:
                    continue

                new_imbalance = max(
                    abs(new_current_width - previous_width),
                    abs(new_following_width - new_current_width),
                )
                if new_following_width - new_current_width >= later_line_gap:
                    continue
                if new_imbalance >= original_imbalance:
                    continue

                candidate = (
                    new_imbalance,
                    new_penalty,
                    abs(new_current_width - new_following_width),
                    -new_current_width,
                    cut,
                )
                if best is None or candidate < best:
                    best = candidate

            if best is None:
                continue

            cut = best[4]
            polished[index + 1] = current[:cut]
            polished[index + 2] = current[cut:] + following
            changed = True

        for index in range(1, len(polished) - 1):
            current = polished[index]
            current_width = text_width(current)
            if current_width >= min_width - 6:
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


def wrap_japanese_legacy(
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
            wrap_japanese_legacy(chunk, target, min_ratio, engine, sudachi_mode, naturalness_weight)
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
            first_line_shortness = 0
            if start == 0 and end != n and line_width < min_width:
                first_line_shortness = (min_width - line_width) ** 2 * 20
            candidate_cost = (
                cost[start]
                + raggedness
                + first_line_shortness
                + naturalness * naturalness_weight
            )

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


def mechanical_boundaries(text: str, target: int) -> list[int]:
    """Return rightmost width-limited boundaries without language judgment."""
    widths = width_prefixes(text)
    boundaries = []
    start = 0
    while start < len(text):
        end = start
        while end < len(text) and widths[end + 1] - widths[start] <= target:
            end += 1
        if end == start:
            end += 1
        boundaries.append(end)
        start = end
    return boundaries


def wrap_japanese_cost(
    text: str,
    target: int = 86,
    min_ratio: float = 0.86,
    engine: str = "auto",
    sudachi_mode: str = "C",
    acceptable_cost: float = DEFAULT_ACCEPTABLE_COST,
) -> str:
    """Wrap from full lines, retreating only until each boundary is acceptable."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    if not text:
        return ""
    if (engine == "sudachi" or (engine == "auto" and dictionary is not None)) and len(
        text.encode("utf-8")
    ) > 40000:
        lines = []
        for chunk in split_long_text(text):
            lines.extend(
                wrap_japanese_cost(
                    chunk,
                    target,
                    min_ratio,
                    engine,
                    sudachi_mode,
                    acceptable_cost,
                ).splitlines()
            )
        return "\n".join(lines)

    widths = width_prefixes(text)
    min_width = max(1, math.ceil(target * min_ratio))
    penalties = choose_break_penalties(text, engine, sudachi_mode)
    lines = []
    boundaries = []
    start = 0

    while start < len(text):
        hard_end = start
        while hard_end < len(text) and widths[hard_end + 1] - widths[start] <= target:
            hard_end += 1
        if hard_end >= len(text):
            lines.append(text[start:].strip())
            boundaries.append(len(text))
            start = len(text)
            break

        acceptable = []
        fallback = []
        for end in range(hard_end, start, -1):
            line_width = widths[end] - widths[start]
            cost = line_break_cost(text, start, end, target, penalties)
            fallback.append((cost, target - line_width, -end, end))
            if cost <= acceptable_cost:
                acceptable.append((line_width < min_width, target - line_width, cost, -end, end))

        if acceptable:
            end = min(acceptable)[4]
        else:
            end = min(fallback)[3]
        lines.append(text[start:end].strip())
        boundaries.append(end)
        start = end

    if start < len(text):
        lines.append(text[start:].strip())
        boundaries.append(len(text))
    initial_boundaries = boundaries[:]
    boundaries = rebalance_cost_boundaries(
        text,
        boundaries,
        target,
        min_width,
        penalties,
        acceptable_cost,
    )
    if any(
        line_break_cost(
            text,
            boundaries[i - 1] if i else 0,
            boundary,
            target,
            penalties,
        )
        > acceptable_cost
        for i, boundary in enumerate(boundaries[:-1])
    ):
        boundaries = initial_boundaries
    boundaries = reduce_acceptable_later_gaps(
        text,
        boundaries,
        target,
        min_width,
        engine,
        sudachi_mode,
        acceptable_cost,
    )
    output = []
    start = 0
    for end in boundaries:
        output.append(text[start:end].strip())
        start = end
    return "\n".join(line for line in output if line)


def wrap_japanese_global_cost(
    text: str,
    target: int = 86,
    min_ratio: float = 0.86,
    engine: str = "auto",
    sudachi_mode: str = "C",
    naturalness_weight: float = 8.0,
) -> str:
    """Choose line boundaries together using semantic and visual costs."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    if not text:
        return ""
    if (engine == "sudachi" or (engine == "auto" and dictionary is not None)) and len(
        text.encode("utf-8")
    ) > 40000:
        return "\n".join(
            wrap_japanese_global_cost(
                chunk,
                target,
                min_ratio,
                engine,
                sudachi_mode,
                naturalness_weight,
            )
            for chunk in split_long_text(text)
        )

    widths = width_prefixes(text)
    total_width = widths[-1]
    if total_width <= target:
        return text

    min_width = max(1, math.ceil(target * min_ratio))
    relaxed_min_width = max(1, min_width - 6)
    final_orphan_width = max(1, min_width - 30)
    penalties = choose_break_penalties(text, engine, sudachi_mode)
    boundary_weight = naturalness_weight / 2
    minimum_lines = max(1, math.ceil(total_width / target))
    candidate_ends = [0]
    candidate_ends.extend(
        end
        for end in range(1, len(text))
        if global_line_break_cost(text, 0, end, target, penalties) < FORBIDDEN_BREAK_COST
    )
    candidate_ends.append(len(text))

    for line_count in range(minimum_lines, minimum_lines + 4):
        # State includes the prior line start so a longer following line can be penalized.
        states: dict[tuple[int, int], tuple[float, list[int]]] = {(0, 0): (0.0, [])}
        for line_number in range(1, line_count + 1):
            remaining_lines = line_count - line_number
            next_states: dict[tuple[int, int], tuple[float, list[int]]] = {}
            for (prior_start, start), (old_score, old_path) in states.items():
                prior_width = widths[start] - widths[prior_start] if line_number > 1 else None
                for end in candidate_ends:
                    if end <= start:
                        continue
                    line_width = widths[end] - widths[start]
                    if line_width > target:
                        break

                    remaining_width = total_width - widths[end]
                    if remaining_width > remaining_lines * target:
                        continue
                    if remaining_lines and remaining_width == 0:
                        continue
                    if (line_number == line_count) != (end == len(text)):
                        continue

                    boundary_cost = 0.0
                    if end != len(text):
                        boundary_cost = global_line_break_cost(text, start, end, target, penalties)
                        if boundary_cost >= FORBIDDEN_BREAK_COST:
                            continue
                        shortfall = max(0, relaxed_min_width - line_width)
                        visual_cost = (target - line_width) ** 2 + shortfall**2 * 8
                    else:
                        shortfall = max(0, final_orphan_width - line_width)
                        visual_cost = shortfall**2 * GLOBAL_ORPHAN_WEIGHT

                    later_gap_cost = 0.0
                    if prior_width is not None:
                        excess_gap = max(
                            0,
                            line_width - prior_width - GLOBAL_LATER_GAP_ALLOWANCE,
                        )
                        later_gap_cost = excess_gap**2 * GLOBAL_LATER_GAP_WEIGHT

                    score = (
                        old_score
                        + visual_cost
                        + later_gap_cost
                        + boundary_cost * boundary_weight
                    )
                    key = (start, end)
                    best = next_states.get(key)
                    if best is None or score < best[0]:
                        next_states[key] = (score, old_path + [end])
            states = next_states
            if not states:
                break

        completed = [
            result for (start, end), result in states.items() if end == len(text)
        ]
        if completed:
            path = min(completed, key=lambda result: result[0])[1]
            path = reduce_acceptable_later_gaps(
                text,
                path,
                target,
                min_width,
                engine,
                sudachi_mode,
                20.0,
                cost_strategy="global-cost",
            )
            path = rebalance_global_residual_gaps(
                text,
                path,
                target,
                min_width,
                penalties,
                20.0,
            )
            lines = []
            start = 0
            for end in path:
                lines.append(text[start:end].strip())
                start = end
            return "\n".join(line for line in lines if line)

    return greedy_wrap(text, target, penalties)


def rebalance_cost_boundaries(
    text: str,
    boundaries: list[int],
    target: int,
    min_width: int,
    penalties: Optional[dict[int, float]],
    acceptable_cost: float,
) -> list[int]:
    """Balance spans without moving nearly full, already acceptable boundaries."""
    if len(boundaries) < 2:
        return boundaries
    widths = width_prefixes(text)
    anchors = [0]
    previous = 0
    for boundary in boundaries[:-1]:
        width = widths[boundary] - widths[previous]
        if (
            len(anchors) == 1
            and width >= target - 2
            and line_break_cost(text, previous, boundary, target, penalties) <= acceptable_cost
        ):
            anchors.append(boundary)
        previous = boundary
    anchors.append(len(text))

    optimized = []
    for span_start, span_end in zip(anchors, anchors[1:]):
        existing = [b for b in boundaries if span_start < b <= span_end]
        line_count = len(existing)
        if line_count <= 1:
            optimized.extend(existing)
            continue

        total_width = widths[span_end] - widths[span_start]
        average = total_width / line_count
        candidate_ends = [
            end
            for end in range(span_start + 1, span_end)
            if semantic_break_cost(text, end, penalties) < FORBIDDEN_BREAK_COST
        ]
        candidate_ends.append(span_end)
        states = {span_start: (0.0, [])}
        for line_number in range(1, line_count + 1):
            next_states = {}
            for start, (old_cost, old_path) in states.items():
                if line_number == line_count:
                    ends = (span_end,)
                else:
                    ends = (end for end in candidate_ends if end > start and end < span_end)
                for end in ends:
                    line_width = widths[end] - widths[start]
                    if line_width > target:
                        break
                    if end != span_end and line_width < min_width - 6:
                        continue
                    remaining_lines = line_count - line_number
                    remaining_width = widths[span_end] - widths[end]
                    if remaining_lines and remaining_width > remaining_lines * target:
                        continue
                    boundary_cost = 0.0
                    if end != span_end:
                        boundary_cost = line_break_cost(text, start, end, target, penalties)
                        if boundary_cost > acceptable_cost:
                            continue
                    score = old_cost + (line_width - average) ** 2 + boundary_cost * 4
                    best = next_states.get(end)
                    if best is None or score < best[0]:
                        next_states[end] = (score, old_path + [end])
            states = next_states
            if not states:
                break
        best = states.get(span_end)
        optimized.extend(best[1] if best is not None else existing)
    return optimized


def reduce_acceptable_later_gaps(
    text: str,
    boundaries: list[int],
    target: int,
    min_width: int,
    engine: str,
    sudachi_mode: str,
    acceptable_cost: float,
    passes: int = 6,
    gap_threshold: int = 12,
    cost_strategy: str = "cost",
) -> list[int]:
    """Move readable material left only when the new boundary remains acceptable."""
    widths = width_prefixes(text)
    refined = boundaries[:]
    cost_function = (
        global_line_break_cost if cost_strategy == "global-cost" else line_break_cost
    )
    for _ in range(passes):
        changed = False
        for index in range(len(refined) - 1):
            start = refined[index - 1] if index else 0
            current_end = refined[index]
            following_end = refined[index + 1]
            current_width = widths[current_end] - widths[start]
            following_width = widths[following_end] - widths[current_end]
            if following_width - current_width < gap_threshold:
                continue

            previous_width = None
            if index:
                previous_start = refined[index - 2] if index > 1 else 0
                previous_width = widths[start] - widths[previous_start]
            third_width = None
            if index + 1 < len(refined) - 1:
                third_end = refined[index + 2]
                third_width = widths[third_end] - widths[following_end]
            combined = text[start:following_end]
            try:
                local_penalties = choose_break_penalties(combined, engine, sudachi_mode)
            except RuntimeError:
                local_penalties = None
            best = None
            for new_end in range(current_end + 1, following_end):
                new_current_width = widths[new_end] - widths[start]
                if new_current_width > target:
                    break
                new_following_width = widths[following_end] - widths[new_end]
                prefix = text[current_end:new_end]
                remaining = text[new_end:following_end]
                completes_quotation = closes_quotation_before_reporting(prefix, remaining)
                allows_short_reporting_line = (
                    completes_quotation and new_following_width >= min_width - 12
                )
                if (
                    index + 1 < len(refined) - 1
                    and new_following_width < min_width - 6
                    and not allows_short_reporting_line
                ):
                    continue
                cost = cost_function(
                    combined,
                    0,
                    new_end - start,
                    target,
                    local_penalties,
                )
                if cost > acceptable_cost:
                    continue
                if third_width is not None:
                    old_worst_later_gap = max(
                        following_width - current_width,
                        third_width - following_width,
                        0,
                    )
                    new_worst_later_gap = max(
                        new_following_width - new_current_width,
                        third_width - new_following_width,
                        0,
                    )
                    if new_worst_later_gap > old_worst_later_gap:
                        continue
                    next_combined = text[new_end:third_end]
                    try:
                        next_penalties = choose_break_penalties(
                            next_combined,
                            engine,
                            sudachi_mode,
                        )
                    except RuntimeError:
                        next_penalties = None
                    next_cost = cost_function(
                        next_combined,
                        0,
                        following_end - new_end,
                        target,
                        next_penalties,
                    )
                    if next_cost > acceptable_cost:
                        continue
                keeps_readable_phrase = is_readable_moved_prefix(prefix, remaining)
                old_neighbor_gaps = [abs(following_width - current_width)]
                new_neighbor_gaps = [abs(new_following_width - new_current_width)]
                if previous_width is not None:
                    old_neighbor_gaps.append(abs(current_width - previous_width))
                    new_neighbor_gaps.append(abs(new_current_width - previous_width))
                if third_width is not None:
                    old_neighbor_gaps.append(abs(third_width - following_width))
                    new_neighbor_gaps.append(abs(third_width - new_following_width))
                old_imbalance = max(old_neighbor_gaps)
                new_imbalance = max(new_neighbor_gaps)
                if new_imbalance > old_imbalance or (
                    new_imbalance == old_imbalance and not keeps_readable_phrase
                ):
                    continue
                candidate = (
                    new_imbalance,
                    cost,
                    abs(new_following_width - new_current_width),
                    target - new_current_width,
                    -new_end,
                    new_end,
                )
                if best is None or candidate < best:
                    best = candidate
            if best is not None:
                refined[index] = best[5]
                changed = True
        if not changed:
            break
    return refined


def rebalance_global_residual_gaps(
    text: str,
    boundaries: list[int],
    target: int,
    min_width: int,
    penalties: Optional[dict[int, float]],
    acceptable_cost: float,
    gap_threshold: int = 12,
) -> list[int]:
    """Reflow a paragraph only when it removes a remaining later-line gap."""
    if len(boundaries) < 2:
        return boundaries

    widths = width_prefixes(text)

    def residual_break_cost(start: int, end: int) -> float:
        cost = global_line_break_cost(text, start, end, target, penalties)
        if cost <= acceptable_cost:
            return cost
        before = text[:end]
        after = text[end:]
        if before.endswith("ための") and after.startswith("一覧を"):
            raw = boundary_penalty(text, end, penalties)
            return FORBIDDEN_BREAK_COST if raw == math.inf else raw
        if before.endswith(("引き寄せた", "持ち替えた")) and after.startswith("あと、「"):
            return 18
        return cost

    def path_metrics(path: list[int]) -> tuple[int, int, int, list[int]]:
        line_widths = []
        start = 0
        for end in path:
            line_widths.append(widths[end] - widths[start])
            start = end
        gaps = [
            following - current
            for current, following in zip(line_widths, line_widths[1:])
        ]
        return (
            sum(gap >= gap_threshold for gap in gaps),
            max((abs(gap) for gap in gaps), default=0),
            sum(abs(gap) for gap in gaps),
            line_widths,
        )

    original_metrics = path_metrics(boundaries)
    if original_metrics[0] == 0:
        return boundaries

    line_count = len(boundaries)
    relaxed_min_width = max(1, min_width - 6)
    existing_final_width = original_metrics[3][-1]
    candidate_ends = [0]
    candidate_ends.extend(
        end
        for end in range(1, len(text))
        if residual_break_cost(0, end) <= acceptable_cost
    )
    candidate_ends.append(len(text))

    # State includes the previous start so adjacent line differences can be scored.
    states: dict[
        tuple[int, int],
        tuple[int, int, int, float, list[int]],
    ] = {(0, 0): (0, 0, 0, 0.0, [])}
    for line_number in range(1, line_count + 1):
        remaining_lines = line_count - line_number
        next_states: dict[
            tuple[int, int],
            tuple[int, int, int, float, list[int]],
        ] = {}
        for (prior_start, start), (
            flagged_gaps,
            max_gap,
            total_gap,
            boundary_total,
            old_path,
        ) in states.items():
            prior_width = widths[start] - widths[prior_start] if line_number > 1 else None
            for end in candidate_ends:
                if end <= start:
                    continue
                line_width = widths[end] - widths[start]
                if line_width > target:
                    break
                if end != len(text) and line_width < relaxed_min_width:
                    continue
                if end == len(text) and line_width < existing_final_width:
                    continue
                if (line_number == line_count) != (end == len(text)):
                    continue
                if widths[-1] - widths[end] > remaining_lines * target:
                    continue

                boundary_cost = 0.0
                if end != len(text):
                    boundary_cost = residual_break_cost(start, end)
                    if boundary_cost > acceptable_cost:
                        continue

                new_flagged = flagged_gaps
                new_max_gap = max_gap
                new_total_gap = total_gap
                if prior_width is not None:
                    gap = line_width - prior_width
                    new_flagged += gap >= gap_threshold
                    new_max_gap = max(new_max_gap, abs(gap))
                    new_total_gap += abs(gap)

                candidate = (
                    new_flagged,
                    new_max_gap,
                    new_total_gap,
                    boundary_total + boundary_cost,
                    old_path + [end],
                )
                key = (start, end)
                best = next_states.get(key)
                if best is None or candidate[:4] < best[:4]:
                    next_states[key] = candidate
        states = next_states
        if not states:
            return boundaries

    completed = [
        candidate
        for (start, end), candidate in states.items()
        if end == len(text)
    ]
    if not completed:
        return boundaries
    best = min(completed, key=lambda candidate: candidate[:4])
    replacement = best[4]
    replacement_metrics = path_metrics(replacement)
    if (
        replacement_metrics[0] < original_metrics[0]
        and replacement_metrics[1] <= original_metrics[1]
    ):
        return replacement
    return boundaries


def wrap_japanese(
    text: str,
    target: int = 86,
    min_ratio: float = 0.86,
    engine: str = "auto",
    sudachi_mode: str = "C",
    naturalness_weight: float = 8.0,
    strategy: str = "legacy",
    acceptable_cost: float = DEFAULT_ACCEPTABLE_COST,
) -> str:
    if strategy == "legacy":
        return wrap_japanese_legacy(
            text,
            target,
            min_ratio,
            engine,
            sudachi_mode,
            naturalness_weight,
        )
    if strategy == "global-cost":
        return wrap_japanese_global_cost(
            text,
            target,
            min_ratio,
            engine,
            sudachi_mode,
            naturalness_weight,
        )
    return wrap_japanese_cost(
        text,
        target,
        min_ratio,
        engine,
        sudachi_mode,
        acceptable_cost,
    )


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


def wrap_document(
    text: str,
    target: int = 86,
    min_ratio: float = 0.86,
    engine: str = "auto",
    sudachi_mode: str = "C",
    naturalness_weight: float = 8.0,
    input_breaks: str = "preserve",
    strategy: str = "legacy",
    acceptable_cost: float = DEFAULT_ACCEPTABLE_COST,
) -> str:
    source_lines = text.splitlines() if input_breaks == "preserve" else reflow_paragraphs(text)
    wrapped = []
    for source_line in source_lines:
        if not source_line.strip():
            wrapped.append("")
            continue
        wrapped.append(
            wrap_japanese(
                source_line,
                target,
                min_ratio,
                engine,
                sudachi_mode,
                naturalness_weight,
                strategy,
                acceptable_cost,
            )
        )
    return "\n".join(wrapped)


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
    parser.add_argument(
        "--input-breaks",
        choices=("preserve", "reflow"),
        default="preserve",
        help="preserve existing lines, or reflow nonblank paragraph lines before wrapping",
    )
    parser.add_argument(
        "--strategy",
        choices=("legacy", "cost", "global-cost"),
        default="legacy",
        help="legacy is stable; cost and global-cost are comparison strategies",
    )
    parser.add_argument(
        "--acceptable-cost",
        type=float,
        default=DEFAULT_ACCEPTABLE_COST,
        help="highest boundary unnaturalness accepted by the cost strategy",
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
        output = wrap_document(
            text,
            args.target,
            args.min_ratio,
            args.engine,
            args.sudachi_mode,
            args.naturalness_weight,
            args.input_breaks,
            args.strategy,
            args.acceptable_cost,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
