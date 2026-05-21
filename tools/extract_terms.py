#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from glossary_common import read_text


TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z .'-]{1,40}|[\u30a0-\u30ffー]{2,20}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract candidate proper terms from a source chapter.")
    parser.add_argument("file")
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--out")
    args = parser.parse_args()

    text = read_text(Path(args.file))
    counts = Counter(match.group(0).strip() for match in TOKEN_RE.finditer(text))
    terms = [(term, count) for term, count in counts.most_common() if count >= args.min_count]

    output = "\n".join(f"{term}\t{count}" for term, count in terms)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

