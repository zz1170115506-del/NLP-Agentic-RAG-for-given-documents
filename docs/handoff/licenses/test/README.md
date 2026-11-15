---
license: mit
language:
  - en
task_categories:
  - question-answering
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: test
        path: test.jsonl
---

# COMP5423 BrowseComp-Plus Test Set

Test questions for the COMP5423 Skill-Augmented Search Agent project, released on November 12, 2026.

- [test.jsonl](test.jsonl): 100 questions. Each line contains only `id` and `question`; reference answers are not provided.
- [Validation set and submission example](https://huggingface.co/datasets/HongruCai/COMP5423-BrowseComp-Plus-Val).

Questions are sampled from [BrowseComp-Plus](https://huggingface.co/datasets/Tevatron/browsecomp-plus) and do not overlap with the course validation set. Use the same full [document collection](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus) for retrieval.
