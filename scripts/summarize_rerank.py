"""Audit real evaluator artifacts and build a text-free descriptive analysis bundle.

Example: python scripts/summarize_rerank.py --runs dev=outputs/rerank-eval/round1 \
    --labels data/rerank-eval/labels.jsonl --output outputs/rerank-eval/analysis
Cross-run pairing is explicit: --compare reference:C=optimized:C. Only compare
the same frozen questions/corpus/candidate pools; never combine dev and heldout.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics


METRICS = ("evidence_candidate_hit", "evidence_hit_at_k", "evidence_mrr", "evidence_recall_at_k",
           "document_hit_at_k", "document_mrr", "document_recall_at_k")
TIMINGS = ("retrieval_seconds", "rerank_seconds", "total_seconds")
BLOCKER = ("固定小语料上的人工编写、非随机抽样诊断题；没有独立重复实验或随机种子重复。"
           "主题内查询相关，因此不把查询、片段或重复读取当作独立实验。"
           "不执行总体显著性检验，不声称全量课程表现或总体胜出。")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def percentile(values, probability):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * probability
    lower = int(pos)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (pos - lower)


def descriptive(values):
    values = [float(x) for x in values if x is not None]
    if not values:
        return {"n": 0, "mean": None, "sd": None, "median": None, "min": None, "max": None}
    if any(not math.isfinite(x) for x in values):
        raise ValueError("Nonfinite metric/timing value")
    return {"n": len(values), "mean": statistics.mean(values),
            "sd": statistics.stdev(values) if len(values) > 1 else None,
            "median": statistics.median(values), "min": min(values), "max": max(values)}


def cluster_interval(pairs, reps=5000, seed=20261111):
    """Descriptive sensitivity to resampling observed topics, NOT population CI."""
    clusters = defaultdict(list)
    for cluster, value in pairs:
        if value is not None:
            clusters[cluster].append(float(value))
    if len(clusters) < 2:
        return {"cluster_count": len(clusters), "interval": None, "reason": "fewer_than_two_topics"}
    rng, keys, samples = random.Random(seed), sorted(clusters), []
    for _ in range(reps):
        resampled = [v for key in rng.choices(keys, k=len(keys)) for v in clusters[key]]
        samples.append(statistics.mean(resampled))
    return {"cluster_count": len(keys), "interval": [percentile(samples, .025), percentile(samples, .975)],
            "repetitions": reps, "seed": seed,
            "meaning": "95% percentile interval under resampling observed topic clusters; conditional sensitivity, not population confidence"}


def safe_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError("Run labels must contain only letters, digits, hyphens and underscores")
    return name


def load_labels(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate label IDs")
    topics = sorted({row.get("topic_group", row["id"]) for row in rows})
    mapping = {topic: f"topic-{i:02d}" for i, topic in enumerate(topics, 1)}
    # Drop answers and spans immediately. The analysis consumes only saved metrics.
    return {row["id"]: {"split": row["split"], "topic": mapping[row.get("topic_group", row["id"])]}
            for row in rows}


def valid(row):
    return (row["status"] == "success" and row["annotation_available"]
            and row["category"] not in {"invalid_label", "document_labels_only", "unlabeled"})


def read_run(name, path, labels, label_hash):
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["labels_sha256"] != label_hash:
        raise ValueError(f"{name}: label file differs from frozen run")
    expected = manifest["sample_ids"]
    if len(set(expected)) != len(expected) or any(key not in labels for key in expected):
        raise ValueError(f"{name}: duplicate/unknown sample IDs")
    manifest_id, records, raw_by_id = digest_json(manifest), [], {}
    for file in sorted((path / "queries").glob("*.json")):
        row = json.loads(file.read_text())
        key = row["id"]
        if key not in expected or key in raw_by_id or row["manifest_id"] != manifest_id:
            raise ValueError(f"{name}: per-query identity mismatch")
        raw_by_id[key] = row
    if not raw_by_id:
        raise ValueError(f"{name}: no completed query artifacts; no report can be generated")
    pool_pairs = 0
    for key in expected:
        raw = raw_by_id.get(key, {})
        groups = raw.get("groups", {})
        b, c = groups.get("B", {}), groups.get("C", {})
        if b.get("status") == c.get("status") == "success":
            if not b.get("pool_sha256") or b["pool_sha256"] != c.get("pool_sha256"):
                raise ValueError(f"{name}/{key}: B/C did not share the exact candidate pool")
            def identities(item):
                return sorted((h["doc_id"], h["chunk_id"]) for h in item["ordered"])
            if identities(b) != identities(c):
                raise ValueError(f"{name}/{key}: reranking lost or added candidates")
            pool_pairs += 1
        for group in ("A", "B", "C"):
            result = groups.get(group, {"status": "missing"})
            metric, timing, diag = result.get("metrics", {}), result.get("timing", {}), result.get("diagnostics", {})
            first = metric.get("evidence_first_rank")
            if first is not None and (type(first) is not int or not 1 <= first <= len(result.get("ordered", []))):
                raise ValueError(f"{name}/{key}/{group}: impossible evidence rank")
            if metric.get("annotation_available") and metric.get("evidence_mrr") is not None:
                if not math.isclose(metric["evidence_mrr"], 1 / first if first else 0.0, abs_tol=1e-12):
                    raise ValueError(f"{name}/{key}/{group}: MRR contradicts rank")
                if bool(metric["evidence_hit_at_k"]) != bool(first and first <= manifest["top_k"]):
                    raise ValueError(f"{name}/{key}/{group}: top-k hit contradicts rank")
            if result.get("status") == "success":
                ordered = result["ordered"]
                final = [[h["doc_id"], h["chunk_id"]] for h in ordered[:manifest["top_k"]]]
                if final != result.get("final_ids"):
                    raise ValueError(f"{name}/{key}/{group}: final IDs contradict ordering")
            clean = {"run": name, "group": group, "id": key, **labels[key],
                     "status": result["status"], "error_type": result.get("error_type"),
                     "category": metric.get("category", result["status"]),
                     "annotation_available": bool(metric.get("annotation_available")),
                     "evidence_first_rank": first, "pool_sha256": result.get("pool_sha256"),
                     "retrieval_timing_reused": bool(timing.get("retrieval_timing_reused")),
                     "scored_candidates": diag.get("scored_candidates"),
                     "scored_windows": diag.get("scored_windows"),
                     "peak_rss_bytes": raw.get("peak_rss_bytes")}
            first_hit = result["ordered"][first-1] if first else {}
            clean.update({"first_evidence_doc_id": first_hit.get("doc_id"),
                          "first_evidence_chunk_id": first_hit.get("chunk_id"),
                          "first_evidence_start": first_hit.get("start"),
                          "first_evidence_end": first_hit.get("end")})
            clean.update({key: metric.get(key) for key in METRICS})
            clean.update({key: timing.get(key) for key in TIMINGS})
            for field in (*METRICS, *TIMINGS):
                if clean[field] is not None and (not math.isfinite(clean[field]) or clean[field] < 0):
                    raise ValueError(f"{name}: invalid numeric field {field}")
            records.append(clean)
    model_metadata = []
    for raw in raw_by_id.values():
        model = raw.get("groups", {}).get("C", {}).get("diagnostics", {}).get("model")
        if model and model not in model_metadata:
            model_metadata.append(model)
    index_meta = {key: {"sha256": value["sha256"],
                       "model_id": value["content"].get("model_id"),
                       "resolved_revision": value["content"].get("resolved_revision"),
                       "tokenizer_revision": value["content"].get("tokenizer_revision"),
                       "embedding_backend": value["content"].get("embedding_backend")}
                  for key, value in manifest.get("index_manifests", {}).items()}
    provenance = {"run": name, "run_directory": str(path), "manifest_sha256": sha256(manifest_path),
                  "git_sha": manifest.get("git_sha"), "source_digest": manifest.get("source_digest"),
                  "config_id": manifest["config_id"], "split": manifest["split"],
                  "requested_queries": len(expected), "completed_queries": len(raw_by_id),
                  "sample_ids": expected, "top_k": manifest["top_k"],
                  "baseline_depth": manifest["baseline_depth"], "candidate_depth": manifest["candidate_depth"],
                  "rerank_depth": manifest["rerank_depth"], "retrieval_method": manifest["retrieval_method"],
                  "corpus": manifest["corpus"], "index_manifests": index_meta,
                  "reranker_models": model_metadata, "bc_exact_pool_pairs": pool_pairs,
                  "questions_sha256": manifest["questions_sha256"], "labels_sha256": label_hash,
                  "timing_protocol": manifest["timing_protocol"], "environment": manifest["environment"],
                  "replay": manifest.get("replay")}
    return manifest, records, provenance


def summarize_groups(records, reps):
    groups = {}
    for run, group in dict.fromkeys((row["run"], row["group"]) for row in records):
        rows = [row for row in records if row["run"] == run and row["group"] == group]
        usable = [row for row in rows if valid(row)]
        summary = {"requested": len(rows), "success": sum(r["status"] == "success" for r in rows),
                   "valid_labeled": len(usable), "topics": len({r["topic"] for r in usable}),
                   "status_counts": dict(Counter(r["status"] for r in rows)),
                   "category_counts": dict(Counter(r["category"] for r in rows)),
                   "sample_ids": [r["id"] for r in usable], "metrics": {}, "timing": {}}
        for metric in METRICS:
            values = [(r["topic"], r[metric]) for r in usable]
            summary["metrics"][metric] = {**descriptive([v for _, v in values]),
                                         "topic_resampling": cluster_interval(values, reps)}
        for field in TIMINGS:
            summary["timing"][field] = descriptive([r[field] for r in rows if r["status"] == "success"])
        summary["retrieval_timing_reused_rows"] = sum(r["retrieval_timing_reused"] for r in rows)
        groups[f"{run}:{group}"] = summary
    return groups


def compare(left, right, records, manifests, reps):
    left_run, left_group = left.split(":")
    right_run, right_group = right.split(":")
    if (left_run not in manifests or right_run not in manifests
            or left_group not in {"A", "B", "C"} or right_group not in {"A", "B", "C"}):
        raise ValueError("Unknown comparison endpoint")
    a, b = manifests[left_run], manifests[right_run]
    for key in ("questions_sha256", "labels_sha256", "sample_ids", "corpus", "top_k", "retrieval_method"):
        if a[key] != b[key]:
            raise ValueError(f"Comparison {left}={right} is not paired: {key} differs")
    left_rows = {r["id"]: r for r in records if r["run"] == left_run and r["group"] == left_group}
    right_rows = {r["id"]: r for r in records if r["run"] == right_run and r["group"] == right_group}
    pairs = []
    for key in a["sample_ids"]:
        x, y = left_rows[key], right_rows[key]
        if not valid(x) or not valid(y):
            continue
        if left_run != right_run and left_group == right_group == "C" and x["pool_sha256"] != y["pool_sha256"]:
            raise ValueError(f"Cross-run reranker comparison {key} changed its candidate pool")
        pairs.append({"id": key, "topic": x["topic"],
                      "hit_delta": int(y["evidence_hit_at_k"]) - int(x["evidence_hit_at_k"]),
                      "mrr_delta": y["evidence_mrr"] - x["evidence_mrr"],
                      "left_rank": x["evidence_first_rank"], "right_rank": y["evidence_first_rank"],
                      "left_chunk_id": x["first_evidence_chunk_id"], "right_chunk_id": y["first_evidence_chunk_id"],
                      "total_seconds_delta": y["total_seconds"] - x["total_seconds"],
                      "rerank_seconds_delta": y["rerank_seconds"] - x["rerank_seconds"]})
    result = {"left": left, "right": right, "requested_pairs": len(a["sample_ids"]), "valid_pairs": len(pairs),
              "excluded_pairs": len(a["sample_ids"]) - len(pairs), "rows": pairs,
              "improved": sum(r["hit_delta"] > 0 for r in pairs), "tied": sum(r["hit_delta"] == 0 for r in pairs),
              "regressed": sum(r["hit_delta"] < 0 for r in pairs),
              "entered_top_k": [r["id"] for r in pairs if r["hit_delta"] > 0],
              "dropped_top_k": [r["id"] for r in pairs if r["hit_delta"] < 0],
              "config_changed_keys": [key for key in a["config"] if a["config"][key] != b["config"].get(key)]}
    for field in ("hit_delta", "mrr_delta", "total_seconds_delta", "rerank_seconds_delta"):
        result[field] = {**descriptive([r[field] for r in pairs]),
                         "topic_resampling": cluster_interval([(r["topic"], r[field]) for r in pairs], reps)}
    return result


def fmt(value, digits=3):
    return "NA" if value is None else f"{value:.{digits}f}"


def summary_table(groups):
    rows = ["| Run:group | Valid / requested | Topics | Candidate hit | Evidence Hit@k | Evidence MRR | Document Hit@k | Median total s |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key, group in groups.items():
        metric = group["metrics"]
        values = [fmt(metric[field]["mean"]) for field in
                  ("evidence_candidate_hit", "evidence_hit_at_k", "evidence_mrr", "document_hit_at_k")]
        rows.append(f"| {key} | {group['valid_labeled']} / {group['requested']} | {group['topics']} | "
                    + " | ".join(values) + f" | {fmt(group['timing']['total_seconds']['median'])} |")
    return "\n".join(rows)


def pair_table(comparisons):
    rows = ["| Comparison (right − left) | Pairs | Hit improve / tie / regress | Δ Hit percentage points | Δ MRR | Δ median total s |",
            "|---|---:|---:|---:|---:|---:|"]
    for pair in comparisons:
        hit = pair["hit_delta"]["mean"]
        rows.append(f"| {pair['right']} − {pair['left']} | {pair['valid_pairs']} | "
                    f"{pair['improved']} / {pair['tied']} / {pair['regressed']} | "
                    f"{fmt(100 * hit if hit is not None else None, 1)} | {fmt(pair['mrr_delta']['mean'])} | "
                    f"{fmt(pair['total_seconds_delta']['median'])} |")
    return "\n".join(rows)


def read_integrated_latency(path, provenance):
    """Recompute timing summaries from real repeated unified-search measurements."""
    directory = path if path.is_dir() else path.parent
    manifest_path, summary_path = directory / "manifest.json", directory / "summary.json"
    manifest, supplied = json.loads(manifest_path.read_text()), json.loads(summary_path.read_text())
    if manifest.get("labels_loaded") is not False:
        raise ValueError("Integrated timing must consume unlabeled questions only")
    expected, repeat_count = manifest["question_ids"], manifest["repeats"]
    if len(expected) != len(set(expected)) or not expected or type(repeat_count) is not int or repeat_count < 1:
        raise ValueError("Invalid integrated timing sample/repeat count")
    manifest_id, records = digest_json(manifest), {}
    known = {item["manifest_sha256"]: item for item in provenance}
    references = {}
    for group, reference in manifest["reference_snapshots"].items():
        if reference["manifest_sha256"] not in known:
            raise ValueError("Include the integrated benchmark's reference runs in --runs")
        references[group] = (Path(known[reference["manifest_sha256"]]["run_directory"]), reference["result_group"])
    for file in sorted((directory / "queries").glob("*.json")):
        row = json.loads(file.read_text())
        if row["manifest_id"] != manifest_id or row["id"] not in expected or row["id"] in records:
            raise ValueError("Integrated timing per-query identity mismatch")
        records[row["id"]] = row
    if set(records) != set(expected):
        raise ValueError("Integrated timing is incomplete; do not present a complete timing summary")
    query_medians, group_names = [], ("B", "C", "D")
    for index, key in enumerate(expected):
        row = records[key]
        rotations = [list(group_names[(index+r) % 3:] + group_names[:(index+r) % 3]) for r in range(repeat_count)]
        if row["execution_orders"] != rotations:
            raise ValueError("Integrated timing order does not match the frozen rotation protocol")
        for group in group_names:
            result = row["groups"][group]
            samples = result["measurements"]
            if len(samples) != repeat_count or [s["repeat"] for s in samples] != list(range(1, repeat_count+1)):
                raise ValueError("Integrated timing repeat count/sequence mismatch")
            for index_repeat, sample in enumerate(samples):
                if sample["pool_sha256"] != row["candidate_pool"]["sha256"] or sample["final_ids"] != result["final_ids"]:
                    raise ValueError("Integrated timing changed candidates/final results across repeats")
                if sample["order_position"] != rotations[index_repeat].index(group) + 1:
                    raise ValueError("Integrated timing measurement has an incorrect order position")
                if sample["rerank_status"] != ("disabled" if group == "B" else "success"):
                    raise ValueError("Integrated timing silently fell back or failed")
                if any(not math.isfinite(sample[t]) or sample[t] < 0 for t in TIMINGS):
                    raise ValueError("Invalid integrated timing observation")
            if group in references:
                source_dir, source_group = references[group]
                filename = hashlib.sha256(key.encode()).hexdigest()[:24] + ".json"
                frozen = json.loads((source_dir / "queries" / filename).read_text())["groups"][source_group]
                if frozen["pool_sha256"] != row["candidate_pool"]["sha256"] or frozen["final_ids"] != result["final_ids"]:
                    raise ValueError("Integrated timing differs from its original ranking reference")
            clean = {"id": key, "group": group, "technical_repeats": repeat_count}
            for timing in TIMINGS:
                observed = statistics.median(s[timing] for s in samples)
                if not math.isclose(observed, result[f"median_{timing}"], rel_tol=1e-12, abs_tol=1e-12):
                    raise ValueError("Integrated stored query median contradicts measurements")
                clean[f"median_{timing}"] = observed
            query_medians.append(clean)
    result = {"query_count": len(expected), "unit_of_analysis": "query median across repeated measurements",
              "repeats_are_independent_samples": False, "groups": {}, "paired_latency": {},
              "pool_identity_verified_across_all_groups_and_repeats": True,
              "final_ids_stable_across_repeats": True, "frozen_reference_checked": bool(references),
              "sample_ids": expected, "peak_rss_bytes": max(r["peak_rss_bytes"] for r in records.values()),
              "sessions": sorted({r["session_id"] for r in records.values()})}
    lookup = {(row["id"], row["group"]): row for row in query_medians}
    for group in group_names:
        rows = [row for row in query_medians if row["group"] == group]
        result["groups"][group] = {"query_count": len(rows), "repeat_count_per_query": repeat_count,
            **{f"median_query_median_{key}": statistics.median(r[f"median_{key}"] for r in rows) for key in TIMINGS},
            "mean_query_median_total_seconds": statistics.mean(r["median_total_seconds"] for r in rows)}
    for left, right in (("B", "C"), ("C", "D"), ("B", "D")):
        before = [lookup[key, left]["median_total_seconds"] for key in expected]
        after = [lookup[key, right]["median_total_seconds"] for key in expected]
        delta = [b-a for a, b in zip(before, after, strict=True)]
        result["paired_latency"][f"{right}_vs_{left}"] = {
            "paired_queries": len(delta), "median_query_total_delta_seconds": statistics.median(delta),
            "median_query_total_ratio": statistics.median(b/a for a, b in zip(before, after, strict=True)),
            "faster_queries": sum(v < 0 for v in delta), "slower_queries": sum(v > 0 for v in delta),
            "unchanged_queries": sum(v == 0 for v in delta)}
    if result != supplied:
        raise ValueError("Integrated summary contradicts independently recomputed measurements")
    result["per_query_medians"] = query_medians
    result["provenance"] = {"run_directory": str(directory), "manifest_sha256": sha256(manifest_path),
        "source_summary_sha256": sha256(summary_path), "git_sha": manifest["git_sha"],
        "source_digest": manifest["source_digest"], "config_ids": manifest["config_ids"],
        "rerank_depths": {group: config["rerank_depth"] for group, config in manifest["configs"].items()},
        "questions_sha256": manifest["questions_sha256"], "corpus_fingerprint": manifest["corpus"]["fingerprint"],
        "index_manifest_sha256": manifest["index_manifest_sha256"], "reference_snapshots": manifest["reference_snapshots"],
        "timing": manifest["timing"], "order": manifest["order"], "warmup": manifest["warmup"],
        "rss_scope": manifest["rss_scope"], "threads": manifest["threads"], "packages": manifest["packages"]}
    return result


def write_figures(output, groups, records):
    # Import only when actual validated artifacts exist; never generate mock evidence.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import Normalize

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "pdf.fonttype": 42, "ps.fonttype": 42})
    directory = output / "figures"
    directory.mkdir(exist_ok=True)
    # A/B in a replay are exact historical copies, so do not draw them as new data.
    names = [name for name, group in groups.items()
             if name.endswith(":C") or group["retrieval_timing_reused_rows"] != group["requested"]]
    x = np.arange(len(names))
    fig, axes = plt.subplots(1, 3, figsize=(max(11, len(names) * .9), 4), constrained_layout=True)
    for ax, metric, title in zip(axes,
        ("evidence_candidate_hit", "evidence_hit_at_k", "evidence_mrr"),
        ("Annotated evidence in candidates", "Annotated evidence in top k", "Reciprocal first evidence rank"), strict=True):
        means = [groups[name]["metrics"][metric]["mean"] for name in names]
        colors = {"A": "#4C78A8", "B": "#F2A541", "C": "#2A9D8F"}
        ax.bar(x, [v if v is not None else np.nan for v in means], color=[colors[name.split(":")[1]] for name in names])
        for i, name in enumerate(names):
            bounds = groups[name]["metrics"][metric]["topic_resampling"]["interval"]
            if bounds is not None:
                ax.vlines(i, bounds[0], bounds[1], color="#222222", linewidth=1.2)
                ax.hlines(bounds, i-.08, i+.08, color="#222222", linewidth=1.2)
        ax.set_ylim(0, 1.08)
        ax.set_xticks(x, names, rotation=55, ha="right")
        ax.set_title(title)
        ax.set_ylabel("Observed proportion / mean")
        ax.grid(axis="y", alpha=.18)
    fig.suptitle("Fixed diagnostic sample; intervals resample observed topics only", fontsize=11)
    for suffix in ("png", "pdf"):
        fig.savefig(directory / f"figure-01-main-comparison.{suffix}", dpi=180)
    plt.close(fig)

    ids = list(dict.fromkeys(row["id"] for row in records))
    matrix = np.full((len(ids), len(names)), np.nan)
    rank_text = {}
    for row in records:
        if valid(row) and f"{row['run']}:{row['group']}" in names:
            i, j = ids.index(row["id"]), names.index(f"{row['run']}:{row['group']}")
            matrix[i, j] = row["evidence_mrr"]
            rank_text[i, j] = str(row["evidence_first_rank"]) if row["evidence_first_rank"] else "miss"
    fig, (ax, latency) = plt.subplots(1, 2, figsize=(max(12, len(names) * 1.25), max(5, len(ids) * .3)),
                                     gridspec_kw={"width_ratios": [1.7, 1]}, constrained_layout=True)
    cmap = plt.get_cmap("Blues").copy()
    cmap.set_bad("#EEEEEE")
    picture = ax.imshow(matrix, cmap=cmap, norm=Normalize(0, 1), aspect="auto")
    ax.set_xticks(range(len(names)), names, rotation=55, ha="right")
    ax.set_yticks(range(len(ids)), ids)
    for (i, j), text in rank_text.items():
        ax.text(j, i, text, ha="center", va="center", fontsize=8,
                color="white" if matrix[i, j] > .6 else "#222222")
    ax.set_title("First annotated evidence rank (miss = outside candidate pool)")
    fig.colorbar(picture, ax=ax, shrink=.65, label="Reciprocal rank; gray = unavailable")
    for index, name in enumerate(names):
        run, group = name.split(":")
        rows = [r for r in records if r["run"] == run and r["group"] == group and r["status"] == "success"]
        values = [r["total_seconds"] for r in rows if r["total_seconds"] is not None]
        jitter = [(i - (len(values)-1)/2) * .025 for i in range(len(values))]
        latency.scatter([index+j for j in jitter], values, color="#4C78A8", alpha=.65, s=20)
        if values:
            latency.hlines(statistics.median(values), index-.2, index+.2, color="#B44636", linewidth=2)
    latency.set_xticks(range(len(names)), names, rotation=55, ha="right")
    latency.set_ylabel("Warm query total seconds")
    latency.set_title("One observed timing/query; red = median")
    latency.grid(axis="y", alpha=.18)
    for suffix in ("png", "pdf"):
        fig.savefig(directory / f"figure-02-rank-cost.{suffix}", dpi=180)
    plt.close(fig)


def write_integrated_figure(output, result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = {(r["id"], r["group"]): r for r in result["per_query_medians"]}
    depths = result["provenance"]["rerank_depths"]
    ids, names = result["sample_ids"], ("B", f"C{depths['C']}", f"D{depths['D']}")
    repeat_count = result["groups"]["B"]["repeat_count_per_query"]
    fig, (ax, ratios) = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for key in ids:
        values = [rows[key, group]["median_total_seconds"] for group in ("B", "C", "D")]
        ax.plot(range(3), values, marker="o", alpha=.5, linewidth=.8, color="#6B7E8F", markersize=3)
    medians = [result["groups"][group]["median_query_median_total_seconds"] for group in ("B", "C", "D")]
    ax.scatter(range(3), medians, color="#B44636", s=65, marker="D", zorder=5,
               label=f"Median of {len(ids)} query medians")
    ax.set_xticks(range(3), names)
    ax.set_ylabel("Actual search wall time (seconds)")
    ax.set_title(f"Each line = one query median of {repeat_count} repeats")
    ax.grid(axis="y", alpha=.2)
    ax.legend(frameon=False, fontsize=8)
    values = [rows[key, "D"]["median_total_seconds"] / rows[key, "C"]["median_total_seconds"] for key in ids]
    ratios.bar(range(len(ids)), values, color="#2A9D8F")
    ratios.axhline(1., color="#555555", linestyle="--", label="Equal latency")
    ratios.axhline(statistics.median(values), color="#B44636", linewidth=1.5, label="Median paired ratio")
    ratios.set_xticks(range(len(ids)), ids, rotation=55, ha="right")
    ratios.set_ylabel(f"{names[2]} / {names[1]} query-median latency")
    ratios.set_ylim(0, 1.1)
    ratios.set_title("Same query, same candidate pool")
    ratios.legend(frameon=False, fontsize=8)
    fig.suptitle("Integrated unified search; technical repeats do not increase accuracy sample size", fontsize=10)
    for suffix in ("png", "pdf"):
        fig.savefig(output / "figures" / f"figure-03-integrated-latency.{suffix}", dpi=180)
    plt.close(fig)


def integrated_section(result):
    lines = ["## 补充：统一 search 的直接重复计时", "",
             "本节是对实际 `SearchService.search` 的完整查询墙钟计时；三模型在同一进程中常驻，"
             "预热后轮换 B/C/D 的执行顺序。哈希核对开销在计时之外。它取代回放组合值作为实际查询延迟的主要依据。",
             f"共有 {result['query_count']} 道查询，每配置每题 "
             f"{result['groups']['B']['repeat_count_per_query']} 次技术重复。先对每题取中位数，再汇总题目中位数；"
             f"准确率样本量仍为 {result['query_count']}，不能乘以技术重复次数。", "",
             "| Configuration | Queries | Repeats per query | Median query-median total s | Retrieval s | Rerank s |",
             "|---|---:|---:|---:|---:|---:|"]
    for key, value in result["groups"].items():
        lines.append(f"| {key} | {value['query_count']} | {value['repeat_count_per_query']} | "
                     f"{fmt(value['median_query_median_total_seconds'],6)} | "
                     f"{fmt(value['median_query_median_retrieval_seconds'],6)} | "
                     f"{fmt(value['median_query_median_rerank_seconds'],6)} |")
    lines += ["", "各列分别取中位数，所以检索与重排列不必精确加和等于总耗时列。", "",
              "| Paired comparison | Queries | Median total delta s | Median paired ratio | Faster / tied / slower |",
              "|---|---:|---:|---:|---:|"]
    for name, value in result["paired_latency"].items():
        lines.append(f"| {name} | {value['paired_queries']} | {fmt(value['median_query_total_delta_seconds'],6)} | "
                     f"{fmt(value['median_query_total_ratio'],6)} | {value['faster_queries']} / "
                     f"{value['unchanged_queries']} / {value['slower_queries']} |")
    ratio = result["paired_latency"]["D_vs_C"]["median_query_total_ratio"]
    lines += ["", f"D10/C30 的逐题耗时比中位数为 {ratio:.6f}，对应约 {(1-ratio)*100:.1f}% 的典型配对降幅。"
              "这是观测到的本机代价变化，不是跨设备或跨会话性能保证。",
              "全部重复的候选池和最终结果均与冻结参考相符；重复没有产生新的准确率证据。",
              "![统一搜索直接重复计时](figures/figure-03-integrated-latency.png)", "",
              "图 3 左侧每条线代表一题的三次计时中位数，右侧给出同题 D10/C30 比值。"
              "它支持把 D10 作为较低开销的可选重排配置；能否推荐重排仍须结合保留集的证据退化。",
              f"进程峰值 RSS 为 {result['peak_rss_bytes']} 字节，包含三套模型与运行时；不能解释为重排器单独内存。",
              "原始技术重复留在本地，脱敏摘要和逐题中位数见 `integrated-summary.json`。", ""]
    return lines


def write_bundle(output, payload):
    groups, comparisons = payload["groups"], payload["comparisons"]
    lines = ["# 固定语料重排：严格描述性分析", "", "## 分析问题", "",
             "B−A 检查扩大候选深度；C−B 在同一候选池内检查本地重排。显式跨运行对照检查第二轮单因素修改。",
             "主指标为已标注原文证据 Hit@k；候选覆盖、首证据 MRR、文档命中和预热后耗时分别报告。", "",
             "## 已核验数据与准确数字", "", summary_table(groups), "", pair_table(comparisons), "",
             "有效配对仅包含两端成功且具备有效片段标注的题目；降级、失败和未完成均单独保留，未伪装成重排成功。",
             "所有 B/C 成功对照已核验候选池 SHA256 和候选 ID 集相同。按题目 ID 配对，不能把片段当作样本。", "",
             "回放运行中的 A/B 是原候选与原计时的副本，不是新增独立实验；各运行单独列出，不合并扩充样本量。", "",
             "## 图与解释", "", "![固定样本命中与排名](figures/figure-01-main-comparison.png)", "",
             "图 1 区分候选是否含证据和最终是否呈现证据。只有候选覆盖相同的 C−B 对照能用于判断排序作用。",
             "误差线是对已观察主题组重抽样的 95% 条件区间，用于查看小样本敏感性；不代表总体置信区间。", "",
             "图中省略回放 A/B 的重复列，完整数值仍保留在表格与 JSON 中。", "",
             "![逐题排名与耗时](figures/figure-02-rank-cost.png)", "",
             "图 2 展示是哪道题发生了变化，以及每个实际查询的耗时。红线为中位数，没有把单次运行误作多次重复。",
             "跨运行回放会复用原检索耗时；仅重排耗时是新测量，因此总耗时属于组合估计，不是一次新的端到端计时。", "",
             "## 失败、范围和不确定性", "", BLOCKER,
             "部分证据标签只衡量已标注范围；未命中标注不等于没有任何有效证据。未标注候选的相关性未知。",
             "未提供独立全量测试、官方课程验证题或跨会话独立重复数据，因此这些结果不能支持课程 EM、总体泛化或稳定尾延迟结论。", "",
             "## Claim Candidates", ""]
    lines += ["### 逐题复核入口", "",
              "| Comparison | ID | First evidence rank | First evidence chunk before → after |",
              "|---|---|---|---|"]
    for pair in comparisons:
        changed = [r for r in pair["rows"] if r["left_rank"] != r["right_rank"]]
        unchanged = next((r for r in pair["rows"] if r["left_rank"] == r["right_rank"]), None)
        for row in changed + ([unchanged] if unchanged else []):
            lines.append(f"| {pair['left']} → {pair['right']} | {row['id']} | {row['left_rank']} → {row['right_rank']} | "
                         f"`{row['left_chunk_id']}` → `{row['right_chunk_id']}` |")
    lines += ["", "数值不变的样本用于核对持平行为；排名变化不一定跨越 top_k 边界。", ""]
    for pair in comparisons:
        name = f"{pair['right']} 相对 {pair['left']}"
        lines += [f"- Claim: {name} 的已标注证据呈现表现由冻结样本配对结果描述。",
                  f"  - Source evidence: metrics.json 的 comparisons；有效配对 {pair['valid_pairs']}。",
                  f"  - Allowed wording: Hit@k 改善 / 持平 / 退化为 {pair['improved']} / {pair['tied']} / {pair['regressed']}；"
                  f"平均 MRR 差 {fmt(pair['mrr_delta']['mean'])}。",
                  "  - Forbidden stronger wording: 显著提高总体正确率、已证明全量收益或已证明课程成绩提高。",
                  "  - Uncertainty: 人工诊断题、部分标签、较少独立主题；单次查询计时。",
                  "  - Next check: 在未参与选择的主题和官方验证题上检查覆盖与端到端回答。",
                  "  - Decision: keep（仅保留样本内描述）", ""]
    if payload.get("integrated_latency"):
        lines += integrated_section(payload["integrated_latency"])
    lines += ["## 可追溯产物", "", "- `metrics.json`：完整描述性统计、配对效应与脱敏运行版本。",
              "- `per-query.csv`：样本 ID、状态、排名、命中和计时，不含问题、答案或原文。",
              "- `stats-appendix.md`：统计单位、区间定义和推断边界。",
              "- `figure-catalog.md`：图的用途、观察和解释范围。", ""]
    (output / "analysis-report.md").write_text("\n".join(lines), encoding="utf-8")

    stats = ["# 统计附录", "", "## 单位与效应", "",
             "每个冻结查询在不同配置下配对。主题组为重抽样单位，保留组内所有题目；组内题目不视为独立重复。",
             "主效应为 Hit@k 的配对绝对差（百分点），辅助效应为 MRR 差和秒数差。",
             "mean ± SD 描述这组查询的离散程度，不是多种训练种子或重复运行的稳定性。", "",
             "## 条件重抽样", "",
             f"固定 seed=20261111，重复 {payload['resampling_repetitions']} 次。每次等概率有放回抽取原主题组数，"
             "保留抽中主题的全部查询，再计算查询加权均值。表中区间为这些均值的第 2.5/97.5 百分位。",
             "它只检验对已观察主题构成的敏感性。人工选题没有随机抽样总体，因此不称其为总体置信区间。",
             "主题少于两个时不提供区间；全部命中或全不命中可能得到退化区间，不意味着总体没有不确定性。", "",
             "## 显著性和多重比较", "", BLOCKER,
             "不运行 t 检验、秩和检验或符号检验；没有 p 值，也不存在需要 Holm 校正的已执行检验族。",
             "默认对照为各运行的 B−A 和 C−B；跨运行对照由命令明确指定。图和逐题表保留所有对照，不挑最好结果。", "",
             "## 完整描述性统计", "",
             "| Run:group | Metric | n | Mean | SD across queries | Median | Min | Max | 95% topic-resampling interval |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for name, group in groups.items():
        for field, value in {**group["metrics"], **group["timing"]}.items():
            bounds = value.get("topic_resampling", {}).get("interval")
            interval = "NA" if bounds is None else f"[{fmt(bounds[0])}, {fmt(bounds[1])}]"
            stats.append(f"| {name} | {field} | {value['n']} | {fmt(value['mean'])} | {fmt(value['sd'])} | "
                         f"{fmt(value['median'])} | {fmt(value['min'])} | {fmt(value['max'])} | {interval} |")
    stats += ["", "## 失败与缺失", ""]
    for name, group in groups.items():
        stats.append(f"- {name}: 状态 {json.dumps(group['status_counts'], ensure_ascii=False)}；"
                     f"类别 {json.dumps(group['category_counts'], ensure_ascii=False)}。")
    stats += ["", "不删除慢查询或离群值；不报告小样本 p95/p99。峰值 RSS 是进程生命周期高水位，不能解释为重排器增量内存。", ""]
    if payload.get("integrated_latency"):
        stats += integrated_section(payload["integrated_latency"])
        stats += ["三次技术重复用于减小单次计时波动，同一进程与同一查询之间仍有关联。"
                  "它们没有增加独立准确率运行或总体推断的样本数，因此没有新增显著性检验或多重比较检验族。", ""]
    (output / "stats-appendix.md").write_text("\n".join(stats), encoding="utf-8")

    movements = "; ".join(f"{p['right']}−{p['left']}: +/=/− {p['improved']}/{p['tied']}/{p['regressed']}" for p in comparisons)
    catalog = ["# 图目录", "", "## figure-01-main-comparison.pdf / .png", "",
               "- Purpose: 区分候选覆盖变化与同池重排变化。",
               "- Data source: metrics.json/groups，原始运行路径和 manifest 校验值见 provenance。",
               "- Variables: 横轴运行与配置；纵轴候选证据命中率、最终证据命中率和首证据 MRR。",
               "- Caption: 固定样本，标注 k 与每组有效 n；误差线为已观察主题重抽样的 95% 条件区间。",
               f"- Key observation: {movements}。",
               "- Interpretation: 先检查候选覆盖，再用 C−B 判断排序；不能把候选扩大的效果归给重排。",
               "- Decision: 结合配对改善/退化及耗时，在开发样本提出候选配置，再用保留样本复核。",
               "- Caveats: 部分标签、少量人工诊断题；误差线不是总体置信区间。", "",
               "## figure-02-rank-cost.pdf / .png", "",
               "- Purpose: 找出具体变化题目，并检查排序代价。",
               "- Data source: per-query.csv；每个格子和散点对应一次保存的运行。",
               "- Variables: 热图颜色为倒数排名，格内文本为实际排名；miss 表示候选池中未含标注范围；灰色为不存在/失败的组合。",
               "- Caption: 散点是单次预热后查询耗时，红线为中位数；不画重复运行误差条。",
               f"- Key observation: 对照中的进入/掉出数量为 {movements}，具体 ID 在 metrics.json/comparisons。",
               "- Interpretation: 相同均值可能掩盖不同题目的得失；先检查掉出题目，再检查是否发生窗口或预算截断。",
               "- Decision: 选择最常见的失败原因或实际主要耗时因素，保持其他条件固定进行下一轮。",
               "- Caveats: 回放复用检索耗时，总时间是组合估计；单次样本不足以推断尾延迟。", ""]
    if payload.get("integrated_latency"):
        ratio = payload["integrated_latency"]["paired_latency"]["D_vs_C"]["median_query_total_ratio"]
        direct = payload["integrated_latency"]
        catalog += ["## figure-03-integrated-latency.pdf / .png", "",
                    "- Purpose: 以统一 search 的直接计时复核第二轮优化的系统成本。",
                    "- Data source: integrated-summary.json 的 per_query_medians 与来源哈希。",
                    "- Variables: 左侧每题 B/C30/D10 三次技术重复的中位数，红菱形为题目中位数的总体中位数；右侧逐题 D10/C30 比值。",
                    f"- Key observation: D/C 配对比值中位数 {ratio:.6f}，"
                    f"{direct['paired_latency']['D_vs_C']['faster_queries']}/{direct['query_count']} 题更快；"
                    "各配置的输出均与其冻结参考一致。",
                    "- Interpretation: 在已常驻模型和相同池的本机执行条件下，减少评分候选降低了实际查询耗时。",
                    "- Decision: 以直接计时描述性能收益；D10 保持为可选配置，不能用速度收益抵消未修复的证据退化。",
                    f"- Caveats: n={direct['query_count']} 查询，每题 "
                    f"{direct['groups']['B']['repeat_count_per_query']} 次为技术重复；同一进程、单设备，没有总体置信区间或跨会话性能保证。", ""]
    (output / "figure-catalog.md").write_text("\n".join(catalog), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", required=True, metavar="LABEL=DIRECTORY")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", action="append", default=[], metavar="LEFT:GROUP=RIGHT:GROUP")
    parser.add_argument("--resamples", type=int, default=5000)
    parser.add_argument("--latency", type=Path, help="Optional integrated benchmark directory or its summary.json")
    args = parser.parse_args()
    if not 100 <= args.resamples <= 100000:
        parser.error("--resamples must be between 100 and 100000")
    labels, manifests, records, provenance = load_labels(args.labels), {}, [], []
    for specification in args.runs:
        name, location = specification.split("=", 1)
        name = safe_name(name)
        if name in manifests:
            parser.error("Run labels must be unique")
        manifest, rows, source = read_run(name, Path(location), labels, sha256(args.labels))
        manifests[name] = manifest
        records.extend(rows)
        provenance.append(source)
    comparisons = []
    for name in manifests:
        for left, right in (("A", "B"), ("B", "C")):
            comparisons.append(compare(f"{name}:{left}", f"{name}:{right}", records, manifests, args.resamples))
    for specification in args.compare:
        left, right = specification.split("=", 1)
        comparisons.append(compare(left, right, records, manifests, args.resamples))
    payload = {"format_version": 1, "scope": "descriptive_fixed_manual_diagnostic_sample",
               "primary_metric": "annotated_evidence_hit_at_k", "inference_blocker": BLOCKER,
               "resampling_repetitions": args.resamples, "resampling_seed": 20261111,
               "unique_query_count": len({row["id"] for row in records}),
               "replay_policy": "replayed A/B groups repeat prior observations; never pooled or counted as independent samples",
               "groups": summarize_groups(records, args.resamples), "comparisons": comparisons, "provenance": provenance}
    if args.latency:
        payload["integrated_latency"] = read_integrated_latency(args.latency, provenance)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    with (args.output / "per-query.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    write_figures(args.output, payload["groups"], records)
    if payload.get("integrated_latency"):
        (args.output / "integrated-summary.json").write_text(
            json.dumps(payload["integrated_latency"], ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        write_integrated_figure(args.output, payload["integrated_latency"])
    write_bundle(args.output, payload)
    print(json.dumps({"output": str(args.output), "run_labels": list(manifests), "comparisons": len(comparisons),
                      "requested_group_rows": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
