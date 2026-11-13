---
name: search-recovery
description: Recover from zero hits, repeated passages, or searches that fail to supply the next needed fact.
---

Use after an unproductive retrieval or when repeated searches add no relevant evidence. These procedures were authored for this project.

1. State the observable failure briefly: no results, off-topic results, duplicate evidence, or missing relation. Do not claim a passage is absent from the corpus based on one failed search.
2. Inspect the previous query. Retain the rare entity name or distinctive phrase, remove conversational wording, and try the missing relation directly.
3. Change only one search dimension at a time: wording, entity alias found in an observed document, alternate clue, or retrieval method supported by the search tool.
4. If lexical retrieval misses a paraphrase, try an available dense or hybrid mode. If dense retrieval is vague, try an exact entity or distinctive lexical phrase with BM25.
5. Open a promising document or use find_in_document to locate a relevant name, date, institution, or relation. Do not repeatedly search text already inspected.
6. Compare new observations with the current evidence. If no new relevant fact appears after two substantially different attempts, return to another condition or stop with the unresolved condition recorded.

Produce new evidence or an explicit unresolved condition, not an invented answer. All tool modes must be selected from the active tool schema; unavailable indexes are tool errors to handle.
