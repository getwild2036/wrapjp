#!/usr/bin/env python3
"""Evaluate wrapjp against a directory of heterogeneous UTF-8 text files."""

from __future__ import annotations

import argparse
import csv
import math
import re
import time
from pathlib import Path

import japanese_wrap as jw


def compact_content(text: str) -> str:
    return re.sub(r"\s+", "", text)


def paragraph_content(text: str) -> list[str]:
    return [compact_content(paragraph) for paragraph in text.replace("\r\n", "\n").strip().split("\n\n")]


def protected_splits(blocks: list[str]) -> int:
    count = 0
    for block in blocks:
        lines = block.splitlines()
        for first, second in zip(lines, lines[1:]):
            joined = first + second
            boundary = len(first)
            for pattern in jw.PROTECTED_PATTERNS:
                for match in pattern.finditer(joined):
                    if match.start() < boundary < match.end():
                        count += 1
    return count


def boundary_cost_metrics(
    blocks: list[str],
    engine: str,
    acceptable_cost: float,
    target: int,
    strategy: str,
) -> tuple[float, int]:
    total = 0.0
    unacceptable = 0
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        joined = "".join(lines)
        penalties = jw.choose_break_penalties(joined, engine, "C")
        offset = 0
        for index, line in enumerate(lines[:-1]):
            start = offset
            offset += len(line)
            if line[-1:].isascii() and lines[index + 1][:1].isascii():
                cost = 0.0
            elif strategy == "global-cost":
                cost = jw.global_line_break_cost(joined, start, offset, target, penalties)
            else:
                cost = jw.line_break_cost(joined, start, offset, target, penalties)
            total += cost
            if cost > acceptable_cost:
                unacceptable += 1
    return total, unacceptable


def preserve_blocks(source: str, output: str) -> tuple[list[str], int]:
    expected_lines = source.splitlines()
    actual_lines = output.splitlines()
    position = 0
    errors = 0
    blocks = []
    for expected in expected_lines:
        if not expected.strip():
            if position >= len(actual_lines) or actual_lines[position] != "":
                errors += 1
            else:
                position += 1
            continue
        pieces = []
        combined = ""
        expected_compact = compact_content(expected)
        while position < len(actual_lines) and len(combined) < len(expected_compact):
            if actual_lines[position] == "":
                break
            pieces.append(actual_lines[position])
            combined = compact_content("".join(pieces))
            position += 1
        if combined != expected_compact:
            errors += 1
        blocks.append("\n".join(pieces))
    if position != len(actual_lines):
        errors += 1
    return blocks, errors


def residual_improvements(
    paragraphs: list[str],
    target: int,
    min_ratio: float,
    engine: str,
    acceptable_cost: float,
    strategy: str,
) -> int:
    minimum = math.ceil(target * min_ratio)
    count = 0
    for paragraph in paragraphs:
        lines = paragraph.splitlines()
        for index in range(len(lines) - 1):
            current, following = lines[index], lines[index + 1]
            current_width = jw.text_width(current)
            following_width = jw.text_width(following)
            current_gap = following_width - current_width
            if current_gap < 12:
                continue
            slack = target - jw.text_width(current)
            combined = current + following
            penalties = jw.choose_break_penalties(combined, engine, "C")
            for offset in range(1, len(following)):
                prefix = following[:offset]
                prefix_width = jw.text_width(prefix)
                if prefix_width > slack:
                    break
                remaining_width = jw.text_width(following[offset:])
                if prefix.endswith("の") and following[offset : offset + 1] and (
                    jw.is_kanji(following[offset]) or jw.is_katakana(following[offset])
                ) and not jw.is_readable_moved_prefix(prefix, following[offset:]):
                    continue
                if prefix and following[offset : offset + 1] and (
                    jw.is_kanji(prefix[-1]) and jw.is_katakana(following[offset])
                ):
                    continue
                if index + 1 < len(lines) - 1 and remaining_width < minimum - 6:
                    continue
                if strategy == "global-cost":
                    new = jw.global_line_break_cost(
                        combined,
                        0,
                        len(current) + offset,
                        target,
                        penalties,
                    )
                else:
                    new = jw.line_break_cost(
                        combined,
                        0,
                        len(current) + offset,
                        target,
                        penalties,
                    )
                keeps_readable_phrase = jw.is_readable_moved_prefix(
                    prefix,
                    following[offset:],
                )
                previous_width = (
                    jw.text_width(lines[index - 1]) if index > 0 else None
                )
                third_width = (
                    jw.text_width(lines[index + 2]) if index + 2 < len(lines) else None
                )
                if index + 2 < len(lines):
                    if strategy == "global-cost":
                        old_worst_later_gap = max(
                            following_width - current_width,
                            third_width - following_width,
                            0,
                        )
                        new_worst_later_gap = max(
                            remaining_width - (current_width + prefix_width),
                            third_width - remaining_width,
                            0,
                        )
                        if new_worst_later_gap > old_worst_later_gap:
                            continue
                    next_combined = following[offset:] + lines[index + 2]
                    next_penalties = jw.choose_break_penalties(next_combined, engine, "C")
                    if strategy == "global-cost":
                        next_cost = jw.global_line_break_cost(
                            next_combined,
                            0,
                            len(following[offset:]),
                            target,
                            next_penalties,
                        )
                    else:
                        next_cost = jw.line_break_cost(
                            next_combined,
                            0,
                            len(following[offset:]),
                            target,
                            next_penalties,
                        )
                    if next_cost > acceptable_cost:
                        continue
                old_neighbor_gaps = [abs(following_width - current_width)]
                new_neighbor_gaps = [
                    abs(remaining_width - (current_width + prefix_width))
                ]
                if previous_width is not None:
                    old_neighbor_gaps.append(abs(current_width - previous_width))
                    new_neighbor_gaps.append(
                        abs(current_width + prefix_width - previous_width)
                    )
                if third_width is not None:
                    old_neighbor_gaps.append(abs(third_width - following_width))
                    new_neighbor_gaps.append(abs(third_width - remaining_width))
                old_imbalance = max(old_neighbor_gaps)
                new_imbalance = max(new_neighbor_gaps)
                if (
                    new <= acceptable_cost
                    and (
                        new_imbalance < old_imbalance
                        or (
                            new_imbalance == old_imbalance
                            and keeps_readable_phrase
                        )
                    )
                ):
                    count += 1
                    break
    return count


def inspect(path: Path, args: argparse.Namespace, gap_details: list[str]) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    started = time.perf_counter()
    output = jw.wrap_document(
        source,
        args.target,
        args.min_ratio,
        args.engine,
        "C",
        args.naturalness_weight,
        args.input_breaks,
        args.strategy,
        args.acceptable_cost,
    )
    seconds = time.perf_counter() - started

    output_lines = output.splitlines()
    nonblank_widths = [jw.text_width(line) for line in output_lines if line]
    if args.input_breaks == "preserve":
        paragraphs, content_errors = preserve_blocks(source, output)
    else:
        paragraphs = output.split("\n\n")
        content_errors = int(paragraph_content(source) != paragraph_content(output))
    review_cost_limit = (
        max(args.acceptable_cost, 20.0) if args.strategy == "global-cost" else args.acceptable_cost
    )
    boundary_cost, unacceptable_breaks = boundary_cost_metrics(
        paragraphs,
        args.engine,
        review_cost_limit,
        args.target,
        args.strategy,
    )
    first_second_gaps = []
    adjacent_gaps = []
    for paragraph_number, paragraph in enumerate(paragraphs, start=1):
        lines = [line for line in paragraph.splitlines() if line]
        widths = [jw.text_width(line) for line in lines]
        if len(widths) >= 2:
            first_second_gaps.append(widths[1] - widths[0])
        for index in range(len(widths) - 1):
            gap = widths[index + 1] - widths[index]
            adjacent_gaps.append(gap)
            if gap >= args.gap_threshold:
                gap_details.extend(
                    (
                        f"file: {path.name}",
                        f"paragraph/block: {paragraph_number}, lines: {index + 1}-{index + 2}, gap: {gap}",
                        f"[{widths[index]}] {lines[index]}",
                        f"[{widths[index + 1]}] {lines[index + 1]}",
                        "",
                    )
                )

    if args.output_dir:
        output_path = args.output_dir / path.name
        output_path.write_bytes((output.replace("\n", "\r\n") + "\r\n").encode("utf-8"))

    return {
        "file": path.name,
        "source_lines": len(source.splitlines()),
        "output_lines": len(output_lines),
        "seconds": round(seconds, 3),
        "max_width": max(nonblank_widths, default=0),
        "over_target": sum(width > args.target for width in nonblank_widths),
        "content_errors": content_errors,
        "protected_splits": protected_splits(paragraphs),
        "boundary_cost": round(boundary_cost, 3),
        "unacceptable_breaks": unacceptable_breaks,
        "residual_improvements": residual_improvements(
            paragraphs,
            args.target,
            args.min_ratio,
            args.engine,
            review_cost_limit,
            args.strategy,
        ),
        "first_second_gap_ge12": sum(gap >= 12 for gap in first_second_gaps),
        "first_second_gap_ge16": sum(gap >= 16 for gap in first_second_gaps),
        "adjacent_gap_ge12": sum(gap >= 12 for gap in adjacent_gaps),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate wrapjp on heterogeneous documents.")
    parser.add_argument("corpus", type=Path, help="directory containing UTF-8 .txt files")
    parser.add_argument("--input-breaks", choices=("preserve", "reflow"), default="reflow")
    parser.add_argument("--engine", choices=("auto", "sudachi", "rule"), default="auto")
    parser.add_argument("-n", "--target", type=int, default=86)
    parser.add_argument("--min-ratio", type=float, default=0.86)
    parser.add_argument("--naturalness-weight", type=float, default=8.0)
    parser.add_argument("--strategy", choices=("legacy", "cost", "global-cost"), default="global-cost")
    parser.add_argument("--acceptable-cost", type=float, default=jw.DEFAULT_ACCEPTABLE_COST)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path, default=Path("evaluation_report.csv"))
    parser.add_argument("--gap-details", type=Path, help="write text for adjacent later-line gaps")
    parser.add_argument("--gap-threshold", type=int, default=12)
    args = parser.parse_args()

    files = sorted(args.corpus.glob("*.txt"))
    if not files:
        parser.error("the corpus directory contains no .txt files")
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    gap_details: list[str] = []
    rows = [inspect(path, args, gap_details) for path in files]
    with args.report.open("w", newline="", encoding="utf-8-sig") as report:
        writer = csv.DictWriter(report, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    if args.gap_details:
        with args.gap_details.open("w", encoding="utf-8", newline="\r\n") as detail_file:
            if gap_details:
                detail_file.write("\n".join(gap_details))
            else:
                detail_file.write(f"No adjacent later-line gaps >= {args.gap_threshold} were found.\n")

    totals = {
        "documents": len(rows),
        "source_lines": sum(int(row["source_lines"]) for row in rows),
        "over_target": sum(int(row["over_target"]) for row in rows),
        "protected_splits": sum(int(row["protected_splits"]) for row in rows),
        "unacceptable_breaks": sum(int(row["unacceptable_breaks"]) for row in rows),
        "residual_improvements": sum(int(row["residual_improvements"]) for row in rows),
        "gap_ge16": sum(int(row["first_second_gap_ge16"]) for row in rows),
        "seconds": round(sum(float(row["seconds"]) for row in rows), 3),
    }
    print(" ".join(f"{key}={value}" for key, value in totals.items()))
    print(f"report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
