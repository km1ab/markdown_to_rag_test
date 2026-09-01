# Markdown to RAG test

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
~~~

```bash
pip install sudachipy sudachidict_core
```

## Run

```bash
python markdown_to_rag_jsonl.py ./markdown ./rag_documents.jsonl
```

The script recursively reads `.md` and `.markdown` files.

It preserves heading hierarchy and creates:
- `heading_path`
- `content_type`
- `content`
- `embedding_text`
- SudachiPy `tokens`
- `search_tokens`
- `code_blocks`
- `tables`
- `metadata`

It intentionally does not create embeddings. The JSONL is an intermediate dataset so the embedding strategy can be changed later without reparsing the original Markdown.
