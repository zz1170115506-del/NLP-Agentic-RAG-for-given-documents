"""Create public diagnostics from a private workspace, using an explicit output allowlist."""

import argparse
import ast
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re

EXCLUDED = {
    ".git",
    ".venv",
    ".cache",
    ".pytest_cache",
    "__pycache__",
    "site-packages",
    "node_modules",
    "models",
    "q4-weights",
    "crypto-venv",
    "team-extra",
    "team-handoff",
}
COUNTS = set(
    """
    valid formal official_compat strict_grounding records expected completed failed skipped
    attempted_this_run all_attempts_total_tokens all_attempts_tool_calls archived_attempts
    replaced_failed citation_passed tool_calls total_tokens hits losses total_tokens_used errors_count
    valid_existing pending missing ineligible journal_results_reused returncode exit_code bytes
    size sent_bytes total_bytes elapsed_seconds bytes_per_second assets api_requests http_status requests_replayed
    all_questions_rerun_from_empty_state reference_labels_read reported_total_tokens has_answer
    total documents documents_read chunks total_chunks expected_chunks document_count chunk_count
    count rows samples failures vector_rows checked skipped_existing reused correct em usage_complete
    sent uploaded encrypted_parts parts files restored verified valid_record_count formal_grounding_valid
    logical_evidence_files_restored all_original_sha256_matched authenticated_decryption plaintext_bytes
    per_row_bytes source_files_matched downloaded_assets_matched restored_evidence_files_matched
    prompt_tokens completion_tokens complete finished success ok seconds encode_seconds load_seconds
    requests attempts full_corpus_documents full_corpus_source_chunks citation_errors_count
    source_files published_assets downloaded_assets api_calls_in_this_acceptance dimension
    iterations batches batch_size recall mean_latency_seconds tool_result_followup_requests
    answer_matches_synthetic_fixture tests_passed tests_failed tests_skipped records_read
""".split()
)
ENUMS = set(
    """
    completed insufficient_evidence failed error api_error provider_error budget_exceeded max_steps repeated_tool_call
    success succeeded valid invalid verified ready running skipped done incomplete interrupted pending
    started uploaded uploading upload_started upload_complete open sealed restored captured
    restored_and_hash_verified authenticated_and_decrypted sparse encoder instruction hybrid auto
    cpu mps cuda passed pass fail build load encode encoding indexing open_document search
    import index pack restore publish download upload test retry prepare build_index
""".split()
)
ENUM_KEYS = {"status", "state", "stage", "method", "event", "device", "outcome", "kind"}
TIMES = {
    "timestamp_utc",
    "finished_at_hong_kong",
    "started_at_hong_kong",
    "checked_at_utc",
    "checked_at_hong_kong",
    "evaluated_at_utc",
}
DATE = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)?")
ERROR_TYPES = set(
    """
    Arrearage TimeoutError ReadTimeout ConnectTimeout ConnectionError ConnectError HTTPError
    HTTPStatusError RemoteProtocolError PermissionError FileNotFoundError FileExistsError
    KeyboardInterrupt RuntimeError AssertionError ValueError ImportError ModuleNotFoundError
    OSError OperationalError IntegrityError InvalidTag CalledProcessError MemoryError
    JSONDecodeError TypeError KeyError AttributeError IndexError RateLimitError CancelledError
    ConnectionResetError BrokenPipeError SSLError URLError TimeoutExpired BadZipFile
""".split()
)
SUMMARY_RE = re.compile(
    r"^\s*[= ]*((?:\d+ (?:passed|failed|skipped|errors?|warnings?|xfailed|xpassed|deselected)(?:, )?)+) in (\d+(?:\.\d+)?)s\b"
)
PROOF_FILE = re.compile(
    r"(?:verification|verification-result|independent-reuse-verification|source-archive-verification|.*(?:verification|receipt)|.*-audit|.*(?:readiness|quick-check|benchmark|status-before)|.*-monitor|.*-completion-audit|index-acceptance-status|.*摘要|.*核验|.*校验)\.json$",
    re.I,
)
LABELS = {
    "acceptance": "程序验收与基础工具",
    "validation": "验证、测试与失败复盘",
    "retrieval": "语料、索引与检索",
    "publication": "打包、传输与恢复",
    "rerank": "早期重排实验",
    "qwen": "Qwen 九题复测",
    "other": "其他运行与检查",
}


def safe_name(relative):
    if (
        relative.startswith("/")
        or ".." in Path(relative).parts
        or re.search(r"(?i)(?:sk-|gh[pousr]_|github_pat_|bearer\s|[?@=]|[\x00-\x1f])", relative)
    ):
        raise ValueError("Unexpected source label; rename it privately before public export")
    return relative


def stage(label):
    a = label.lower()
    if "qwen4b" in a or "qwen2560" in a:
        return "qwen"
    if "rerank" in a or label.startswith("early-rerank/"):
        return "rerank"
    if any(
        v in a
        for v in (
            "upload",
            "transport",
            "release",
            "publication",
            "download-verification",
            "published-source",
            "handoff",
            "加密",
            "还原",
            "发布核验",
            "archive-verification",
        )
    ):
        return "publication"
    if any(v in a for v in ("qwen-shard", "e5-", "index", "encoder", "instruction", "corpus-", "retrieval")):
        return "retrieval"
    if any(v in a for v in ("validation", "retention", "recovery", "replay", "test100", "bailian", "official-repair")):
        return "validation"
    if any(v in a for v in ("acceptance", "pytest", "install", "unittest", "regression", "dependencies")):
        return "acceptance"
    return "other"


def inventory(roots):
    for label, root in roots:
        if not re.fullmatch("[a-z0-9-]+", label) or not root.is_dir():
            raise ValueError("Each root needs a short public label and an existing directory")
        for base, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(base) / d).is_symlink())
            for name in sorted(names):
                p = Path(base) / name
                if p.is_symlink() or not p.is_file():
                    continue
                public = (
                    safe_name(label + "/" + str(p.relative_to(root))) if p.suffix in {".log", ".out", ".err"} else ""
                )
                if public:
                    yield public, p, "console"
                elif p.suffix == ".json" and ((p.parent / (p.stem + ".log")).is_file() or PROOF_FILE.fullmatch(name)):
                    if p.stat().st_size <= 4_000_000:
                        yield safe_name(label + "/" + str(p.relative_to(root))), p, "checkpoint"


def select_fields(obj):
    """Never export arbitrary strings, messages, commands, identifiers, or raw nested payloads."""
    result = {}
    for key, value in obj.items():
        if key in COUNTS and (type(value) in (bool, int) or type(value) is float and math.isfinite(value)):
            result[key] = value
        elif key in ENUM_KEYS and isinstance(value, str) and value in ENUMS:
            result[key] = value
        elif key in TIMES and isinstance(value, str) and DATE.fullmatch(value):
            result[key] = value
        elif key == "http_statuses" and isinstance(value, list):
            codes = Counter(v for v in value if type(v) is int and 100 <= v < 600)
            if codes:
                result["http_status_counts"] = dict(sorted(codes.items()))
        elif key in ("errors", "record_errors", "formal_grounding_errors") and isinstance(value, list):
            result[key + "_items"] = len(value)
        elif key in ("validation", "metrics", "selected", "totals") and isinstance(value, dict):
            nested = select_fields(value)
            if nested:
                result[key] = nested
        elif key in ("rows", "results", "runs") and isinstance(value, list):
            result[key + "_items"] = len(value)
            # Preserve aggregate provider/status diagnostics without publishing per-row messages.
            statuses = Counter()
            http = Counter()
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                status = entry.get("status")
                if isinstance(status, str) and status in ENUMS:
                    statuses[status] += 1
                codes = entry.get("http_statuses")
                if isinstance(codes, list):
                    http.update(code for code in codes if type(code) is int and 100 <= code < 600)
            if statuses:
                result[key + "_status_counts"] = dict(sorted(statuses.items()))
            if http:
                result[key + "_http_status_counts"] = dict(sorted(http.items()))
    return result


def parse_log(raw):
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    events = []
    whole = None
    try:
        whole = json.loads(text)
    except (ValueError, RecursionError):
        pass
    if isinstance(whole, dict):
        result = select_fields(whole)
        if result:
            events.append({"line": 1, "values": result})
    else:
        decoder = json.JSONDecoder()
        offset = 0
        while offset < len(lines):
            line_no = offset + 1
            line = lines[offset].strip()
            offset += 1
            obj = None
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                except ValueError:
                    if line == "{":
                        try:
                            remainder = "\n".join(lines[line_no - 1 :])
                            obj, end = decoder.raw_decode(remainder)
                            offset = line_no + remainder[:end].count("\n")
                        except ValueError:
                            pass
                    elif line.startswith("{'") and len(line) < 3000:
                        try:
                            obj = ast.literal_eval(line)
                        except (ValueError, SyntaxError):
                            pass
            v = select_fields(obj) if isinstance(obj, dict) else {}
            if not v:
                m = SUMMARY_RE.match(line)
                if m:
                    v = dict((k, int(n)) for n, k in re.findall(r"(\d+) (\w+)", m[1]))
                    v.update(check="pytest", seconds=float(m[2]))
                m = re.match(r"^Ran (\d+) tests? in ([\d.]+)s$", line)
                if m:
                    v = {"check": "unittest", "tests": int(m[1]), "seconds": float(m[2])}
                if line in {"OK", "All checks passed!", "No broken requirements found."}:
                    v = {
                        "check": {
                            "OK": "unittest_ok",
                            "All checks passed!": "ruff_ok",
                            "No broken requirements found.": "pip_check_ok",
                        }[line]
                    }
                m = re.match(r"^Found (\d+) errors?(?: \((\d+) fixed, (\d+) remaining\))?\.", line)
                if m:
                    v = {"check": "ruff", "errors": int(m[1])}
                    if m[2]:
                        v.update(fixed=int(m[2]), remaining=int(m[3]))
                m = re.match(r"^(?:[\w.]+\.)?([A-Za-z]+)(?::|$)", line)
                if m and m[1] in ERROR_TYPES:
                    v = {"exception": m[1]}
                    if "Resume" in line and "mismatch" in line:
                        v["check"] = "resume_identity_mismatch"
                m = re.match(r"^(?:DONE|STAGE_DONE) ([\w.-]+) (\d+(?:\.\d+)?)$", line)
                if m:
                    v = {"check": "stage_completed", "seconds": float(m[2])}
                    if m[1] in ENUMS:
                        v["method"] = m[1]
            if v:
                events.append({"line": line_no, "values": v})
    return len(lines), events


def preference(name):
    copies = (
        "restore",
        "extract",
        "evidence-stage",
        "evidence-package",
        "plaintext-volumes",
        "snapshot",
        "/stage/",
        "/remote-",
        "/source/",
        "release-download",
    )
    return sum(part in name for part in copies), len(Path(name).parts), len(name), name


def generate(roots, output):
    sources = list(inventory(roots))

    def scan(source):
        name, path, kind = source
        payload = path.read_bytes()
        return hashlib.sha256(payload).hexdigest(), name, kind, payload

    by_hash = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for digest, name, kind, payload in pool.map(scan, sources):
            if digest not in by_hash:
                lines, events = parse_log(payload)
                by_hash[digest] = {
                    "sha256": digest,
                    "bytes": len(payload),
                    "line_count": lines,
                    "source_paths": [],
                    "source_types": [],
                    "events": events,
                }
            row = by_hash[digest]
            row["source_paths"].append(name)
            if kind not in row["source_types"]:
                row["source_types"].append(kind)
    buckets = defaultdict(list)
    for row in by_hash.values():
        row["source_paths"].sort(key=preference)
        row["source_types"].sort()
        name = row["source_paths"][0]
        buckets[stage(name)].append(row)
    output.mkdir(exist_ok=True, parents=True)
    intro = [
        "# 项目运行与运维日志",
        "",
        "按阶段打开下表的阅读版，或下载对应的 JSONL。JSONL 每行对应一份内容唯一的源文件，含 SHA-256、来源别名和逐事件行号。相同字节在多个分支、打包目录或下载复原目录出现时只解析一次。来源路径以目录标签开头。",
        "",
        "| 阶段 | 唯一内容 | 来源路径 | 结构化事件 |",
        "|---|---:|---:|---:|",
    ]
    for name, label in LABELS.items():
        rows = sorted(buckets[name], key=lambda row: row["source_paths"][0])
        if not rows:
            continue
        # Keep each downloadable file small enough to browse in GitHub's source viewer.
        batches = [bytearray()]
        for row in rows:
            line = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            if batches[-1] and len(batches[-1]) + len(line) > 700_000:
                batches.append(bytearray())
            batches[-1].extend(line)
        data_links = []
        for i, payload in enumerate(batches, 1):
            suffix = f"-{i:02d}" if len(batches) > 1 else ""
            path = output / f"{name}{suffix}.jsonl"
            path.write_bytes(payload)
            data_links.append(f"[JSONL{suffix}]({path.name})")
        data_links = " · ".join(data_links)
        total = sum(len(r["source_paths"]) for r in rows)
        count = sum(len(r["events"]) for r in rows)
        intro.append(f"| [{label}]({name}.md) · {data_links} | {len(rows)} | {total} | {count} |")
        md = [
            f"# {label}",
            "",
            "表中选取每份文件的关键读数。JSONL 保留所有已识别事件的源行号和完整 SHA-256。复制路径在同一条记录中列举。",
            "",
            f"{data_links} · [全部阶段](README.md)",
            "",
            "| 代表来源 | SHA-256 前 12 位 | 源行 / 导出事件 | 关键读数 |",
            "|---|---|---:|---|",
        ]
        for r in rows:
            picked = []
            events = [e["values"] for e in r["events"]]
            for e in events:
                if e.get("exception") or e.get("check"):
                    picked.append(e)
            if events and events[-1] not in picked:
                picked.append(events[-1])
            summary = "；".join(json.dumps(v, ensure_ascii=False, separators=(",", ":")) for v in picked[-3:])
            if not summary:
                summary = "仅有指纹与行数"
            if len(summary) > 350:
                summary = summary[:349] + "…"
            md.append(
                f"| `{r['source_paths'][0]}` | `{r['sha256'][:12]}` | {r['line_count']} / {len(events)} | {summary} |"
            )
        (output / f"{name}.md").write_text("\n".join(md) + "\n")
    # Show concrete historical checks so the group can start with a human-readable timeline.
    lookups = {path: row for row in by_hash.values() for path in row["source_paths"]}
    selected = [
        ("最初主测试", "work/acceptance/offline/03_main_pytest.log"),
        ("初次九题评估", "work/validation-failure-review/work/validation-review/bailian-evaluation.log"),
        (
            "恢复后的九题评估",
            "work/validation-failure-review/work/validation-review/bailian-evaluation-after-recharge.log",
        ),
        ("证据保留修复的回归测试", "work/validation-failure-review/work/retention-delivery/final-tests.log"),
        ("首次批量上传", "work/release-upload.log"),
        ("分片直传 1", "work/direct-upload-1.log"),
        ("分片直传 2", "work/direct-upload-2.log"),
        ("分片直传 3", "work/direct-upload-3.log"),
    ]
    highlights = []
    for caption, path in selected:
        row = lookups.get(path)
        if not row or not row["events"]:
            continue
        values = row["events"][-1]["values"]
        if "passed" in values:
            message = f"{values['passed']} 项通过，{values.get('failed', 0)} 项失败，{values.get('skipped', 0)} 项跳过"
        elif "rows_http_status_counts" in values:
            message = "百炼响应 " + "、".join(
                f"HTTP {code} 共 {n} 次" for code, n in values["rows_http_status_counts"].items()
            )
        elif "http_status" in values:
            message = f"HTTP {values['http_status']}，状态 {values.get('state', '')}，耗时 {values.get('elapsed_seconds', 0):g} 秒"
        elif "exception" in values:
            message = f"终端以 {values['exception']} 结束"
        else:
            continue
        highlights.append(f"| {caption} | {message} | `{row['sha256'][:12]}` |")
    if highlights:
        intro += ["", "## 可先查看的记录", "", "| 阶段 | 实际读数 | 日志标识 |", "|---|---|---|", *highlights]
    kinds = Counter(kind for _, _, kind in sources)
    intro += [
        "",
        f"共发现 {kinds['console']} 条终端日志路径和 {kinds['checkpoint']} 条结构化检查文件路径，合计 {len(sources)} 条，按内容哈希归并为 {len(by_hash)} 份。",
        "",
        "终端来源包括扩展名为 .log、.out、.err 的项目文件。检查来源包括同名运行旁证 JSON，以及不超过 4 MB 的校验、审计、收据、基准、状态或监测 JSON。源码依赖目录、Git 内部文件和生成本页的工作目录跳过。仅从可识别的日志结构提取通过数、错误类别、HTTP 状态、时间与进度等字段；只有指纹和行数的条目表示导出器未识别其中的公开指标。项目的逐题问答轨迹另见上级目录。",
        "",
        "终端内某一时刻的失败、中断或部分完成只描述该次命令。请结合后续恢复记录及最终验收判断整轮运行。",
        "",
        "来源目录标签：" + "、".join(label for label, _ in roots) + "。",
    ]
    (output / "README.md").write_text("\n".join(intro) + "\n")
    print(
        f"{len(sources)} sources, {len(by_hash)} unique, {sum(len(r['events']) for r in by_hash.values())} public events"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", action="append", required=True, metavar="LABEL=DIR")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    roots = []
    for spec in a.root:
        label, sep, path = spec.partition("=")
        if not sep or label in {n for n, _ in roots}:
            p.error("roots must have unique LABEL=DIR values")
        roots.append((label, Path(path)))
    generate(roots, a.output)


if __name__ == "__main__":
    main()
