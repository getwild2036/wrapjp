# wrapjp

Japanese plain-text line wrapper that balances display width and natural line breaks.

`wrapjp` wraps Japanese text to a target display width, such as 86 half-width
columns. It uses SudachiPy when available and chooses line boundaries across
each paragraph to balance readable Japanese with even line length.

## Features

- Counts display width: ASCII is 1, Japanese full-width characters are 2.
- Uses SudachiPy for Japanese tokenization.
- Falls back to built-in rules when SudachiPy is not installed.
- Avoids common Japanese line-start and line-end problems.
- Prioritizes semantic boundaries after expressions such as `にも` and `または`.
- Protects URLs, DOI strings, email addresses, IDs, versions, and numeric units.
- Keeps lines within the target width.
- Keeps protected strings and tightly connected predicate forms together.
- Allows readable breaks after Japanese `の`, such as `場合の／異常終了`.
- Uses the paragraph-wide `global-cost` strategy by default.
- Preserves line breaks already present in the input text.
- Writes UTF-8 output with Windows `CRLF` line endings when using `-o`.

## Install

```bash
python -m pip install -r requirements.txt
```

On Windows, update an older Git checkout and install dependencies with:

```powershell
git pull origin main
py -m pip install -r requirements.txt
```

## Usage

```bash
python japanese_wrap.py -n 86 --engine sudachi input.txt -o output.txt
```

The normal command above uses the reviewed `global-cost` strategy. On Windows,
use `py` instead of `python`:

```powershell
py japanese_wrap.py -n 86 --engine sudachi input.txt -o output.txt
```

If you want the script to use SudachiPy when installed and fall back otherwise:

```bash
python japanese_wrap.py -n 86 --engine auto input.txt -o output.txt
```

To use the built-in rule engine only:

```bash
python japanese_wrap.py -n 86 --engine rule input.txt -o output.txt
```

For text copied from a PDF or paper, where line breaks inside a paragraph
should be recomposed:

```bash
python japanese_wrap.py -n 86 --engine sudachi --input-breaks reflow paper.txt -o output.txt
```

Blank lines remain paragraph boundaries in `reflow` mode. The default
`preserve` mode keeps every existing input line boundary.

## Options

```text
-n, --target              Target display width. Default: 86
--engine                  auto, sudachi, or rule. Default: auto
--sudachi-mode            A, B, or C. Default: C
--min-ratio               Minimum line width ratio. Default: 0.86
--naturalness-weight      Natural-break weight. Default: 8.0
--input-breaks            preserve or reflow. Default: preserve
--strategy                legacy, cost, or global-cost. Default: global-cost
--acceptable-cost         Maximum accepted break cost in cost mode. Default: 12
-o, --output              Output file path
```

The default `global-cost` strategy considers all line boundaries in a
paragraph together. It scores semantic breaks, unusually short trailing lines,
and cases where a following line becomes noticeably longer. The option can be
omitted in normal use; this explicit command is equivalent:

```bash
python japanese_wrap.py -n 86 --engine sudachi --strategy global-cost input.txt -o output.txt
```

Use `--strategy legacy` only when older output behavior is required. The
`cost` strategy remains available for comparison.

## Example

```bash
python japanese_wrap.py -n 86 --engine sudachi sample_japanese_1000_c.txt -o wrapped.txt
```

The generated sample output in this repository was checked with:

- Maximum width: 86
- Lines over 86: 0
- Too-short non-final lines under the configured minimum: 0
- Detected common word-split patterns: 0

## Corpus Evaluation

Run quality evaluation on a directory of UTF-8 `.txt` files with:

```bash
python evaluate_corpus.py your_corpus --engine sudachi --input-breaks preserve --report evaluation.csv --gap-details gap12_review.txt
```

The report checks display width, content preservation, protected strings such
as DOI and URLs, total boundary cost, remaining breaks above the acceptable
cost, detectable missed natural moves, and visibly large adjacent line-length
gaps. Evaluation also uses `global-cost` by default; pass `--strategy legacy`
when comparing older behavior.
