---
name: search-recovery
description: Recover from empty searches, repeated results, or stalled evidence collection using one controlled query change at a time. Use after a failed search or when no new document supports the pending constraint.
---

# Search recovery

This procedure is original to this fixed-corpus project.

Trigger: the last search found nothing, a tool returned a recoverable error, or successive searches only repeated already inspected evidence.

1. Identify the failure: invalid arguments, overly specific wording, entity ambiguity, or a missing relation.
2. Correct invalid arguments first. For an empty query result, retain one distinctive entity or phrase and remove generic question words. If the entity came from evidence, preserve its original spelling.
3. Make a materially different search: use a shorter anchored query, a documented alternate name, or another available retrieval method. Change one factor so the effect can be inspected.
4. Compare returned document IDs and passages against existing evidence. Open a new relevant passage rather than repeatedly retrieving the same document.
5. Return to the unresolved factual constraint once evidence improves. A successful retrieval alone does not prove the answer.

Expected output: a distinct retry query and new, inspected evidence, or a clear insufficient-evidence termination.

Stop after the configured repeat/tool/step budget. Never manufacture a fact, use a reference answer, fetch source URLs, or repeat the identical failed action to fill the trajectory.
