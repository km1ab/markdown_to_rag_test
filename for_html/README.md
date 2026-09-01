## Usage

```sh
$ python3 html_to_rag_jsonl.py --help
usage: html_to_rag_jsonl.py [-h] [-o OUTPUT] [--chunk-size CHUNK_SIZE] [--overlap OVERLAP] input

HTML → RAG用JSONL変換

positional arguments:
  input                 入力HTMLファイルまたはディレクトリ

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        出力JSONL
  --chunk-size CHUNK_SIZE
  --overlap OVERLAP
```

## How to scraping
### command example

```sh
wget --recursive --level=4 --no-parent --wait=1 \
--random-wait -P ./scraping/html [URL]
```
