#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString


# --------------------------------------------------
# 設定
# --------------------------------------------------

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


# --------------------------------------------------
# HTML → 構造化テキスト
# --------------------------------------------------


def html_to_sections(html_path):
    """
    HTMLを読み込み、

    [
        {
            "heading_path": [...],
            "text": "..."
        },
        ...
    ]

    の形式に変換する。
    """

    html = html_path.read_text(encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")

    # 不要な要素を削除
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()

    root = soup.body or soup

    sections = []

    heading_stack = []

    current_text = []

    def flush_section():
        nonlocal current_text

        text = normalize_text("\n".join(current_text))

        if text:
            sections.append({"heading_path": heading_stack.copy(), "text": text})

        current_text = []

    for element in root.descendants:

        if isinstance(element, NavigableString):
            continue

        tag = element.name

        # ------------------------------------------
        # 見出し
        # ------------------------------------------

        if tag and re.fullmatch(r"h[1-6]", tag):

            flush_section()

            level = int(tag[1])

            heading = normalize_text(element.get_text(" ", strip=True))

            if not heading:
                continue

            # 現在の見出し階層を調整
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(heading)

        # ------------------------------------------
        # 本文
        # ------------------------------------------

        elif tag in ["p", "li", "blockquote", "pre", "td", "th"]:

            text = element.get_text(" ", strip=True)

            text = normalize_text(text)

            if text:
                current_text.append(text)

    flush_section()

    return sections


# --------------------------------------------------
# テキスト正規化
# --------------------------------------------------


def normalize_text(text):
    # NBSP
    text = text.replace("\xa0", " ")

    # 改行コード
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # 空白を整理
    text = re.sub(r"[ \t]+", " ", text)

    # 空行を整理
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


# --------------------------------------------------
# チャンク分割
# --------------------------------------------------


def split_text(text, chunk_size=1000, overlap=150):

    if len(text) <= chunk_size:
        return [text]

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        # できれば文の途中で切らない
        if end < len(text):

            candidates = [
                text.rfind("\n", start, end),
                text.rfind("。", start, end),
                text.rfind("！", start, end),
                text.rfind("？", start, end),
                text.rfind(".", start, end),
            ]

            best = max(candidates)

            if best > start + chunk_size // 2:
                end = best + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks


# --------------------------------------------------
# HTML → JSONL
# --------------------------------------------------


def convert_file(
    html_path, output_path, chunk_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_CHUNK_OVERLAP
):

    sections = html_to_sections(html_path)

    document_id = html_path.name

    chunk_number = 1

    with output_path.open("w", encoding="utf-8") as f:

        for section in sections:

            heading_path = section["heading_path"]
            text = section["text"]

            chunks = split_text(text, chunk_size=chunk_size, overlap=overlap)

            for chunk in chunks:

                record = {
                    "chunk_id": (f"{document_id}:" f"{chunk_number:04d}"),
                    "document_id": document_id,
                    "heading_path": heading_path,
                    "text": chunk,
                }

                f.write(json.dumps(record, ensure_ascii=False) + "\n")

                chunk_number += 1


# --------------------------------------------------
# メイン
# --------------------------------------------------


def main():

    parser = argparse.ArgumentParser(description="HTML → RAG用JSONL変換")

    parser.add_argument("input", help="入力HTMLファイルまたはディレクトリ")

    parser.add_argument("-o", "--output", default="rag.jsonl", help="出力JSONL")

    parser.add_argument("--chunk-size", type=int, default=1000)

    parser.add_argument("--overlap", type=int, default=150)

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    # 単一HTML
    if input_path.is_file():

        convert_file(input_path, output_path, args.chunk_size, args.overlap)

    # ディレクトリ
    elif input_path.is_dir():

        html_files = list(input_path.glob("**/*.html"))
        html_files += list(input_path.glob("**/*.htm"))

        chunk_count = 0

        with output_path.open("w", encoding="utf-8") as f:

            for html_path in html_files:

                sections = html_to_sections(html_path)

                document_id = str(html_path.relative_to(input_path))

                chunk_number = 1

                for section in sections:

                    chunks = split_text(section["text"], args.chunk_size, args.overlap)

                    for chunk in chunks:

                        record = {
                            "chunk_id": (f"{document_id}:" f"{chunk_number:04d}"),
                            "document_id": document_id,
                            "heading_path": section["heading_path"],
                            "text": chunk,
                        }

                        f.write(json.dumps(record, ensure_ascii=False) + "\n")

                        chunk_number += 1
                        chunk_count += 1

        print(f"{len(html_files)} files → " f"{chunk_count} chunks")

    else:
        raise FileNotFoundError(input_path)


if __name__ == "__main__":
    main()
