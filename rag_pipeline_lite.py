#!/usr/bin/env python3

import json
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance


OLLAMA_URL = "http://localhost:11434"

LLM_MODEL = "qwen3:4b"
EMBED_MODEL = "nomic-embed-text"

QDRANT_URL = "http://localhost:6333"
COLLECTION = "sample_rag"


# --------------------------------
# Ollamaに質問する
# --------------------------------

def ollama_generate(prompt):

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    return response.json()["response"]


# --------------------------------
# 要約・キーワード・質問生成
# --------------------------------

def analyze_document(doc):

    prompt = f"""
以下の文章をRAG用に分析してください。

見出し:
{doc["heading_path"]}

本文:
{doc["content"]}

次のJSONだけを返してください。

{{
  "summary": "短い要約",
  "keywords": ["キーワード1", "キーワード2"],
  "questions": [
    "この文章から回答できる質問1",
    "この文章から回答できる質問2"
  ]
}}
"""

    result = ollama_generate(prompt)

    # ```json ... ``` が返ってきても対応
    result = result.strip()

    if result.startswith("```"):
        result = result.split("\n", 1)[1]
        result = result.rsplit("```", 1)[0]

    return json.loads(result)


# --------------------------------
# Embedding
# --------------------------------

def create_embedding(text):

    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={
            "model": EMBED_MODEL,
            "input": text,
        },
        timeout=300,
    )

    response.raise_for_status()

    return response.json()["embeddings"][0]


# --------------------------------
# JSONL読み込み
# --------------------------------

def load_jsonl(filename):

    with open(filename, encoding="utf-8") as f:

        for line in f:

            if not line.strip():
                continue

            yield json.loads(line)


# --------------------------------
# メイン
# --------------------------------

def main():

    documents = list(
        load_jsonl("rag_documents.jsonl")
    )

    print(f"documents: {len(documents)}")


    # --------------------------------
    # Qdrant
    # --------------------------------

    qdrant = QdrantClient(
        url=QDRANT_URL
    )


    # Embedding次元を取得
    test_vector = create_embedding("test")

    vector_size = len(test_vector)

    print("embedding dimension:", vector_size)


    # Collection作成
    collections = [
        c.name
        for c in qdrant.get_collections().collections
    ]

    if COLLECTION not in collections:

        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )


    points = []


    # --------------------------------
    # 文書処理
    # --------------------------------

    with open("rag_enriched.jsonl", "w", encoding="utf-8") as f:
        for index, doc in enumerate(documents):

            print(
                f"[{index + 1}/{len(documents)}]",
                doc["source"],
                doc["heading_path"],
            )


            # ----------------------------
            # Ollamaで分析
            # ----------------------------

            analysis = analyze_document(doc)

            # ----------------------------
            # 解析結果を保存
            # ----------------------------

            enriched = {
                **doc,
                "summary": analysis["summary"],
                "keywords": analysis["keywords"],
                "questions": analysis["questions"],
            }

            f.write(
                json.dumps(
                    enriched,
                    ensure_ascii=False
                ) + "\n"
            )

            # ----------------------------
            # RAG用テキスト
            # ----------------------------

            rag_text = f"""
{doc["heading_path"]}

{doc["content"]}

要約:
{analysis["summary"]}

キーワード:
{", ".join(analysis["keywords"])}

質問:
{" ".join(analysis["questions"])}
""".strip()


            # ----------------------------
            # Embedding
            # ----------------------------

            vector = create_embedding(
                rag_text
            )


            # ----------------------------
            # Qdrant登録
            # ----------------------------

            points.append(

                PointStruct(

                    id=index,

                    vector=vector,

                    payload={

                        "source":
                            doc["source"],

                        "heading_path":
                            doc["heading_path"],

                        "content":
                            doc["content"],

                        "summary":
                            analysis["summary"],

                        "keywords":
                            analysis["keywords"],

                        "questions":
                            analysis["questions"],
                    },
                )
            )


    # --------------------------------
    # 一括登録
    # --------------------------------

    qdrant.upsert(

        collection_name=COLLECTION,

        points=points,
    )


    print()
    print("登録完了")
    print(
        "collection:",
        COLLECTION
    )


if __name__ == "__main__":
    main()