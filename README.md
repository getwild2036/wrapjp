# wrapjp

Japanese plain-text line wrapper that balances display width and natural line breaks.

`wrapjp` wraps Japanese text to a target display width, such as 86 half-width
columns. It uses SudachiPy when available to avoid unnatural breaks inside
Japanese words and phrases, then applies a small polishing pass to reduce short
or awkward lines.

## Features

- Counts display width: ASCII is 1, Japanese full-width characters are 2.
- Uses SudachiPy for Japanese tokenization.
- Falls back to built-in rules when SudachiPy is not installed.
- Avoids common Japanese line-start and line-end problems.
- Keeps lines within the target width.
- Preserves line breaks already present in the input text.
- Writes UTF-8 output with Windows `CRLF` line endings when using `-o`.

## Install

```bash
python -m pip install -r requirements.txt
```

## Usage

```bash
python japanese_wrap.py -n 86 --engine sudachi input.txt -o output.txt
```

If you want the script to use SudachiPy when installed and fall back otherwise:

```bash
python japanese_wrap.py -n 86 --engine auto input.txt -o output.txt
```

To use the built-in rule engine only:

```bash
python japanese_wrap.py -n 86 --engine rule input.txt -o output.txt
```

## Options

```text
-n, --target              Target display width. Default: 86
--engine                  auto, sudachi, or rule. Default: auto
--sudachi-mode            A, B, or C. Default: C
--min-ratio               Minimum line width ratio. Default: 0.86
--naturalness-weight      Natural-break weight. Default: 8.0
-o, --output              Output file path
```

## Example

```bash
python japanese_wrap.py -n 86 --engine sudachi sample_japanese_1000_c.txt -o wrapped.txt
```

The generated sample output in this repository was checked with:

- Maximum width: 86
- Lines over 86: 0
- Too-short non-final lines under the configured minimum: 0
- Detected common word-split patterns: 0
