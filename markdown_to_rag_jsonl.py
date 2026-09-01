#!/usr/bin/env python3
"""
Markdown -> RAG JSONL preprocessor

Features:
- Recursively reads .md / .markdown
- Keeps heading hierarchy
- Unicode NFKC normalization for normal text
- Protects code blocks, URLs, commands, model/product IDs and IPs
- Uses SudachiPy for Japanese tokenization
- Classifies tokens: normal_text / technical_term / command / model_or_product / number / url
- Produces JSONL suitable as an intermediate dataset before embedding/Qdrant
- Does NOT create embeddings

Install:
    pip install sudachipy sudachidict_core

Usage:
    python markdown_to_rag_jsonl.py ./markdown ./rag_documents.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sudachipy import Dictionary, SplitMode


# ----------------------------
# Regexes for protected tokens
# ----------------------------

URL_RE = re.compile(r"https?://[^\s<>()]+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
VERSION_RE = re.compile(r"\bv?\d+(?:\.\d+){1,3}(?:[-+._][A-Za-z0-9.-]+)?\b")
MODEL_ID_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9._:+/-]*){0,3}\b"
)

# Commands / executable-looking names. This is deliberately conservative.
COMMAND_RE = re.compile(
    r"(?<![\w./-])"
    r"(?:sudo\s+)?"
    r"(?:systemctl|journalctl|docker|docker-compose|podman|kubectl|"
    r"python(?:3(?:\.\d+)?)?|pip(?:3)?|uv|git|ssh|scp|curl|wget|"
    r"apt|apt-get|dnf|yum|pacman|npm|node|make|cmake|gcc|g\+\+|"
    r"ffmpeg|ollama|nvidia-smi|vcgencmd|ls|cd|cp|mv|rm|cat|grep|sed|awk|"
    r"find|chmod|chown|systemd-analyze)"
    r"(?:\s+[^\s]+){0,8}",
    re.IGNORECASE,
)

# Common technical terms. Extend this for your own domain.
TECH_TERMS = {
    "RAG", "Embedding", "embedding", "Qdrant", "Ollama", "LLM",
    "BM25", "Reranker", "Reranking", "API", "REST", "HTTP", "HTTPS",
    "JSON", "JSONL", "Markdown", "Docker", "Linux", "Ubuntu",
    "systemd", "timer", "systemctl", "Python", "PyTorch", "CUDA",
    "ComfyUI", "Wan2.2", "GPU", "CPU", "VRAM", "RAM", "NVIDIA",
    "Raspberry", "Raspberry Pi", "Tapo", "P105", "Pro Micro",
    "USB", "LAN", "Wi-Fi", "TCP", "UDP", "DNS", "IP", "IPv4", "IPv6",
    "SSH", "SFTP", "Git", "GitHub", "OCR", "PDF", "AST",
}

# ----------------------------
# Data structures
# ----------------------------

@dataclass
class Protected:
    key: str
    value: str
    kind: str


class Preprocessor:
    def __init__(self) -> None:
        self.tokenizer = Dictionary(dict="core").create(SplitMode.C)

    # ---------- normalization ----------

    @staticmethod
    def normalize_text(text: str) -> str:
        # Normalize Unicode, but do this only on normal prose.
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+\n", "\n\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ---------- markdown parsing ----------

    @staticmethod
    def strip_front_matter(text: str) -> tuple[dict, str]:
        metadata = {}
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                raw = text[4:end]
                # Avoid requiring PyYAML: parse only simple key: value pairs.
                for line in raw.splitlines():
                    m = re.match(r"^\s*([^:#]+?)\s*:\s*(.*?)\s*$", line)
                    if m:
                        metadata[m.group(1).strip()] = m.group(2).strip().strip("\"'")
                text = text[end + 4 :]
        return metadata, text

    @staticmethod
    def parse_blocks(text: str) -> list[dict]:
        """
        Split Markdown into blocks while preserving:
        - headings
        - fenced code blocks
        - paragraphs
        - lists
        - tables
        """
        lines = text.splitlines()
        blocks = []
        i = 0

        while i < len(lines):
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            # Fenced code block
            m = re.match(r"^\s*(```+|~~~+)\s*([A-Za-z0-9_+-]*)\s*$", line)
            if m:
                fence = m.group(1)
                language = m.group(2) or ""
                start = i + 1
                code = []
                i += 1
                while i < len(lines) and not re.match(
                    rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", lines[i]
                ):
                    code.append(lines[i])
                    i += 1
                if i < len(lines):
                    i += 1
                blocks.append({
                    "type": "code",
                    "language": language,
                    "text": "\n".join(code),
                    "line_start": start,
                    "line_end": i,
                })
                continue

            # Heading
            hm = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if hm:
                blocks.append({
                    "type": "heading",
                    "level": len(hm.group(1)),
                    "text": hm.group(2).strip(),
                    "line_start": i + 1,
                    "line_end": i + 1,
                })
                i += 1
                continue

            # Markdown table: collect contiguous table lines.
            if "|" in line and i + 1 < len(lines):
                if re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[i + 1]):
                    table = [line, lines[i + 1]]
                    i += 2
                    while i < len(lines) and "|" in lines[i] and lines[i].strip():
                        table.append(lines[i])
                        i += 1
                    blocks.append({
                        "type": "table",
                        "text": "\n".join(table),
                        "line_start": i - len(table) + 1,
                        "line_end": i,
                    })
                    continue

            # Paragraph/list/quote: collect until blank or special block.
            start = i + 1
            chunk = [line]
            i += 1
            while i < len(lines) and lines[i].strip():
                if re.match(r"^\s*#{1,6}\s+", lines[i]):
                    break
                if re.match(r"^\s*(```+|~~~+)", lines[i]):
                    break
                chunk.append(lines[i])
                i += 1

            blocks.append({
                "type": "text",
                "text": "\n".join(chunk),
                "line_start": start,
                "line_end": i,
            })

        return blocks

    # ---------- token protection ----------

    @staticmethod
    def protect(text: str) -> tuple[str, list[Protected]]:
        protected: list[Protected] = []
        counter = 0

        def repl(kind: str):
            nonlocal counter

            def _r(m: re.Match) -> str:
                nonlocal counter
                key = f"__RAGPROT_{counter}__"
                counter += 1
                protected.append(Protected(key, m.group(0), kind))
                return f" {key} "
            return _r

        # Order matters: URL before generic patterns.
        for regex, kind in [
            (URL_RE, "url"),
            (EMAIL_RE, "url"),
            (IP_RE, "number"),
            (VERSION_RE, "technical_term"),
            (COMMAND_RE, "command"),
        ]:
            text = regex.sub(repl(kind), text)

        return text, protected

    @staticmethod
    def restore(text: str, protected: list[Protected]) -> str:
        for p in protected:
            text = text.replace(p.key, p.value)
        return text

    # ---------- classification ----------

    @staticmethod
    def looks_like_model_or_product(token: str) -> bool:
        patterns = [
            r"^[A-Z]{1,8}\d{1,5}[A-Za-z0-9+_-]*$",
            r"^[A-Za-z]+[0-9]+[A-Za-z0-9+_.-]*$",
            r"^\d{3,5}[A-Za-z][A-Za-z0-9+_.-]*$",
        ]
        return any(re.match(p, token) for p in patterns)

    @staticmethod
    def classify_sudachi_surface(surface: str, normalized: str, pos: list[str]) -> str:
        if URL_RE.fullmatch(surface) or EMAIL_RE.fullmatch(surface):
            return "url"

        if IP_RE.fullmatch(surface) or re.fullmatch(r"\d+(?:\.\d+)?%?", surface):
            return "number"

        if surface.startswith("__RAGPROT_"):
            return "protected"

        if normalized in TECH_TERMS or surface in TECH_TERMS:
            return "technical_term"

        if Preprocessor.looks_like_model_or_product(surface):
            return "model_or_product"

        # Proper nouns / nouns are candidates for technical terms, but don't
        # label every noun as technical. Keep ordinary Japanese as normal_text.
        if pos and pos[0] in {"名詞"}:
            if any(x in surface.lower() for x in (
                "api", "gpu", "cpu", "usb", "lan", "dns", "http",
                "json", "yaml", "pdf", "ocr", "docker", "linux",
            )):
                return "technical_term"

        return "normal_text"

    def analyze(self, text: str) -> dict:
        text = self.normalize_text(text)
        protected_text, protected = self.protect(text)

        tokens = []
        for m in self.tokenizer.tokenize(protected_text):
            surface = m.surface()
            normalized = m.normalized_form()
            pos = m.part_of_speech()
            if not surface.strip():
                continue

            kind = self.classify_sudachi_surface(surface, normalized, pos)
            tokens.append({
                "surface": surface,
                "normalized": normalized,
                "pos": pos,
                "kind": kind,
            })

        # Restore protected placeholders in a second pass.
        for token in tokens:
            token["surface"] = self.restore(token["surface"], protected)
            token["normalized"] = self.restore(token["normalized"], protected)

        # Build grouped searchable text.
        searchable_parts = []
        for token in tokens:
            value = token["normalized"] or token["surface"]
            if value:
                searchable_parts.append(value)

        return {
            "normalized_text": self.restore(protected_text, protected),
            "tokens": tokens,
            "search_tokens": searchable_parts,
            "protected": [
                {"value": p.value, "kind": p.kind}
                for p in protected
            ],
        }

    # ---------- document processing ----------

    def process_file(self, path: Path, root: Path) -> list[dict]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        front_matter, raw = self.strip_front_matter(raw)
        blocks = self.parse_blocks(raw)

        heading_stack: list[str] = []
        records = []

        for block in blocks:
            if block["type"] == "heading":
                level = block["level"]
                heading = self.normalize_text(block["text"])
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(heading)
                continue

            if not block.get("text", "").strip():
                continue

            rel = path.relative_to(root).as_posix()
            content = block["text"]

            if block["type"] == "code":
                normalized_content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
                analysis = {
                    "normalized_text": normalized_content,
                    "tokens": [],
                    "search_tokens": [],
                    "protected": [],
                }
            else:
                analysis = self.analyze(content)
                normalized_content = analysis["normalized_text"]

            record_id_base = f"{rel}:{block['line_start']}"
            digest = hashlib.sha1(record_id_base.encode("utf-8")).hexdigest()[:12]

            code_blocks = []
            if block["type"] == "code":
                code_blocks.append({
                    "language": block.get("language", ""),
                    "code": normalized_content,
                })

            # Heading context is deliberately kept separate from content.
            # The embedding text can later be generated differently.
            embedding_text = "\n".join(
                [
                    " > ".join(heading_stack) if heading_stack else "",
                    normalized_content,
                ]
            ).strip()

            records.append({
                "id": f"{record_id_base}#{digest}",
                "source": rel,
                "heading_path": heading_stack.copy(),
                "heading": heading_stack[-1] if heading_stack else None,
                "level": len(heading_stack),
                "content_type": block["type"],
                "content": normalized_content,
                "embedding_text": embedding_text,
                "tokens": analysis["tokens"],
                "search_tokens": analysis["search_tokens"],
                "code_blocks": code_blocks,
                "tables": [normalized_content] if block["type"] == "table" else [],
                "metadata": {
                    "file": rel,
                    "line_start": block["line_start"],
                    "line_end": block["line_end"],
                    "front_matter": front_matter,
                },
            })

        return records


def iter_markdown_files(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".md", ".markdown"}:
            yield p


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_jsonl", type=Path)
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {args.input_dir}")

    pre = Preprocessor()
    count = 0

    with args.output_jsonl.open("w", encoding="utf-8") as out:
        for path in iter_markdown_files(args.input_dir):
            for record in pre.process_file(path, args.input_dir):
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    print(f"Generated {count} records -> {args.output_jsonl}")


if __name__ == "__main__":
    main()
