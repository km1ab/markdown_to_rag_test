import json

# --------------------------------
# JSONL読み込み
# --------------------------------


def load_jsonl(filename):

    with open(filename, encoding="utf-8") as f:

        for line in f:

            if not line.strip():
                continue

            yield json.loads(line)


document = load_jsonl("./rag_enriched.jsonl")
with open("enriched_only.jsonl", "w") as f:
    for index, doc in enumerate(document):
        d = {
            "index": index,
            "summary": doc["summary"],
            "keywords": doc["keywords"],
            "questions": doc["questions"],
        }

        # print(f"{index}: {d}")
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
