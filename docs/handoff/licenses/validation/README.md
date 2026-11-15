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
      - split: validation
        path: validation.jsonl
---

# COMP5423 BrowseComp-Plus Validation Set

Resources for the COMP5423 Skill-Augmented Search Agent project:

- [validation.jsonl](validation.jsonl): 100 questions with reference answers. Each line contains `id`, `question`, and `answer`.
- [test_prediction.jsonl](examples/test_prediction.jsonl): a submission-format example with an embedded agent trajectory, tool-call count, and total token usage.

Validation questions are sampled from [BrowseComp-Plus](https://huggingface.co/datasets/Tevatron/browsecomp-plus). Use its full [document collection](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus) for retrieval. The course test set is not included.

The prediction example uses `search` and `visit`, with four tool calls and five LLM calls. Its content and token counts are simulated. Real submissions must record actual trajectories and API-reported usage.
