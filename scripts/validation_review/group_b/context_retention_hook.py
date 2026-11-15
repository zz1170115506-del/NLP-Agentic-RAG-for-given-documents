"""Isolated offline/live diagnostic hook; never install into production by default.
Call install('observed-span-diagnostic') in a dedicated serial run before run_question.
The caller must use a separate output directory and record this file's SHA256 plus
condition; model/provider changes are separate conditions. No network calls here.
"""

import builtins
import types

# Public coordinates, selected retrospectively with reference-label access.
# Each condition may retain ONLY evidence already observed in this run's state.
TARGETS = {
    "231": {("43835", 0)},
    "390": {("3282", 750)},
    "58": {("28406", 38250), ("28406", 38806)},
}


def make_wrapper(original, condition, observer=None):
    if condition not in {"observed-span-diagnostic", "focused-tool-first"}:
        raise ValueError("Unknown diagnostic condition")

    def wrapped(state, catalog, groups, settings):
        if condition == "observed-span-diagnostic":
            coordinates = TARGETS.get(state.question.id, set())
            chosen = {ev.evidence_id for ev in state.evidence if (ev.doc_id, ev.offset) in coordinates}
        else:
            # Search observations carry chunk_id; focused open/find spans do not.
            # No question IDs, labels, or hard-coded source coordinates are used.
            chosen = {ev.evidence_id for ev in state.evidence if ev.chunk_id is None}

        def priority_sorted(items, *, key, reverse=False):
            return builtins.sorted(items, key=lambda ev: (ev.evidence_id in chosen, key(ev)), reverse=reverse)

        # Preserve the frozen function's exact code and all other globals. No module
        # global mutation, evidence injection, state mutation, or budget increase.
        changed = types.FunctionType(
            original.__code__,
            {**original.__globals__, "sorted": priority_sorted},
            original.__name__,
            original.__defaults__,
            original.__closure__,
        )
        messages, stats = changed(state, catalog, groups, settings)
        if observer:
            observer(
                {
                    "condition": condition,
                    "question_id": state.question.id,
                    "reference_assisted": condition == "observed-span-diagnostic",
                    "already_observed_prioritized_ids": sorted(chosen),
                    "context_chars": settings.context_chars,
                    "stats": stats,
                }
            )
        return messages, stats

    return wrapped


def install(condition, observer=None):
    """Patch only this diagnostic process; return restore callback."""
    from rag_agent.agent import loop

    original = loop.build_context
    loop.build_context = make_wrapper(original, condition, observer)
    return lambda: setattr(loop, "build_context", original)
