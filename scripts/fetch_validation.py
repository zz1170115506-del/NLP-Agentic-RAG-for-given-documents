"""Download the verified course validation file, without printing its private contents."""
import argparse
from pathlib import Path
import urllib.request
from rag_agent.evaluation import read_questions

p = argparse.ArgumentParser()
p.add_argument('--output', default='data/validation.jsonl')
p.add_argument('--revision', default='277d3b49913c176976e8b40b7df55b00212cf158')
a = p.parse_args()
if not a.revision.isalnum():
    p.error('Use an immutable Hugging Face commit SHA')
url = f'https://huggingface.co/datasets/HongruCai/COMP5423-BrowseComp-Plus-Val/resolve/{a.revision}/validation.jsonl'
path = Path(a.output)
if path.exists():
    p.error('Output already exists; choose another path to preserve it')
path.parent.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(url, timeout=60) as response:
    content = response.read()
path.write_bytes(content)
questions = read_questions(path)
if len(questions) != 100:
    raise ValueError('Expected 100 validation questions; inspect the dataset revision')
print(f'Saved {len(questions)} questions with evaluator-only references to {path}. Revision: {a.revision}')
