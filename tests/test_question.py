import sys
import requests
from qdrant_client import QdrantClient


OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

qdrant = QdrantClient(url="http://localhost:6333")


def embedding(text):

    r = requests.post(
        f"{OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": text}
    )

    r.raise_for_status()

    return r.json()["embeddings"][0]


if __name__ == "__main__":
    question = "水やりは何時に実行される？"
    if len(sys.argv) > 0:
        question = sys.argv[1]

    vector = embedding(question)

    results = qdrant.query_points(
        collection_name="sample_rag",
        query=vector,
        limit=3,
    ).points

    for result in results:

        print("score:", result.score)

        print("source:", result.payload["source"])

        print("heading:", result.payload["heading_path"])

        print("content:", result.payload["content"])

        print("---")
