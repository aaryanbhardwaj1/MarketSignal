"""``python -m marketsignal.evaluation`` - freeze gold, check integrity, run arms.

    freeze     items.json + ingested corpus -> frozen.json (+ alternates review file)
    integrity  frozen.json against the ingested corpus, ledger and items (exit 1 on any problem)
    run        arms over a split -> results.json + report.md

The test split is frozen: ``run --split test`` is refused unless ``--milestone "<reason>"`` is
given, and every test run is appended to ``eval/test-split-log.jsonl`` so its use is auditable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from marketsignal.config import Settings, get_settings
from marketsignal.db.engine import create_engine, create_session_factory
from marketsignal.evaluation import corpus
from marketsignal.evaluation.arms import (
    PIPELINE_ARMS,
    Arm,
    BaselineDenseArm,
    BaselineLexicalArm,
    PipelineArm,
)
from marketsignal.evaluation.dataset import load_frozen, load_items, write_frozen
from marketsignal.evaluation.gold import freeze, integrity_problems
from marketsignal.evaluation.report import build_report, write_report
from marketsignal.evaluation.runner import run_arm, select
from marketsignal.providers.embeddings import Embedder, FastEmbedEmbedder
from marketsignal.providers.rerankers import FastEmbedCrossEncoder
from marketsignal.retrieval.lanes import DocumentFrequencies
from marketsignal.retrieval.pipeline import QueryEmbeddingCache, RetrievalService
from marketsignal.retrieval.rerank import RerankExecutor
from marketsignal.retrieval.types import RetrievalConfig

DATASET_DIR = corpus.EVAL_DIR / "datasets" / "retrieval-v0"
TEST_LOG = corpus.EVAL_DIR / "test-split-log.jsonl"


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 - fixed argv
            capture_output=True,
            text=True,
            check=True,
            cwd=corpus.REPO_ROOT,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _embedder_factory(settings: Settings) -> Callable[[], Embedder]:
    cache: list[Embedder] = []

    def get() -> Embedder:
        if not cache:
            cache.append(
                FastEmbedEmbedder(
                    settings.embed_model_id,
                    settings.embed_model_name,
                    settings.embed_dimensions,
                    settings.model_cache_dir,
                    threads=settings.embed_threads,
                )
            )
        return cache[0]

    return get


ArmBuilder = Callable[[Settings, Callable[[], Embedder]], Arm]
ARMS: dict[str, ArmBuilder] = {
    "baseline-lexical": lambda s, e: BaselineLexicalArm(),
    "baseline-dense": lambda s, e: BaselineDenseArm(e, s),
}


def _decided(path: Path) -> frozenset[tuple[str, str]]:
    """Alternate candidates already judged, plus those removed by the documented prefilter."""
    if not path.exists():
        return frozenset()
    record = json.loads(path.read_text(encoding="utf-8"))
    pairs = {(d["fact_id"], d["handle"]) for d in record.get("decisions", [])}
    for fact_id, handles in record.get("prefilter_dropped", {}).items():
        pairs |= {(fact_id, h) for h in handles}
    return frozenset(pairs)


def _parse_overrides(pairs: list[str]) -> dict[str, Any]:
    """``--set key=value`` -> RetrievalConfig overrides (value parsed as JSON, else string)."""
    fields = RetrievalConfig.__dataclass_fields__
    out: dict[str, Any] = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        if key not in fields:
            raise SystemExit(f"unknown retrieval setting: {key}")
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def _service(
    settings: Settings, embedder: Callable[[], Embedder], overrides: dict[str, Any]
) -> RetrievalService:
    config = RetrievalConfig.from_settings(settings).with_(**overrides)
    reranker = FastEmbedCrossEncoder(
        config.rerank_model, settings.model_cache_dir, threads=settings.rerank_threads
    )
    return RetrievalService(
        config,
        embedder=embedder,
        rerank_executor=RerankExecutor(reranker, settings.rerank_concurrency),
        df_cache=DocumentFrequencies(settings.lexical_idf_cache_size),
        query_cache=QueryEmbeddingCache(0),  # eval measures real embedding latency
    )


async def _freeze(args: argparse.Namespace, settings: Settings) -> int:
    engine = create_engine(settings)
    try:
        items = load_items(args.items)
        dataset, review = await freeze(
            items,
            create_session_factory(engine),
            settings,
            items_sha256=corpus.sha256_bytes(args.items.read_bytes()),
            ledger=corpus.load_ledger(),
            decided=_decided(args.items.parent / "alternates-decisions.json"),
        )
    finally:
        await engine.dispose()
    write_frozen(args.out, dataset)
    args.review.write_text(json.dumps(review, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dataset.manifest["counts"]))
    print(f"alternates to review: {sum(len(v) for v in review.values())} facts -> {args.review}")
    return 0


async def _integrity(args: argparse.Namespace, settings: Settings) -> int:
    engine = create_engine(settings)
    try:
        problems = await integrity_problems(
            load_frozen(args.dataset),
            create_session_factory(engine),
            items_sha256=corpus.sha256_bytes(args.items.read_bytes()),
            ledger=corpus.load_ledger(),
        )
    finally:
        await engine.dispose()
    for problem in problems:
        print(f"FAIL {problem}")
    print("integrity: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
    return 0 if not problems else 1


async def _run(args: argparse.Namespace, settings: Settings) -> int:
    if args.split == "test" and not args.milestone:
        print("refusing to evaluate the frozen test split without --milestone", file=sys.stderr)
        return 2
    dataset = load_frozen(args.dataset)
    items = select(dataset, args.split)
    embedder = _embedder_factory(settings)
    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS and a not in PIPELINE_ARMS]
    if unknown:
        known = sorted([*ARMS, *PIPELINE_ARMS])
        print(f"unknown arms: {unknown}; known: {known}", file=sys.stderr)
        return 2
    overrides = _parse_overrides(args.set or [])
    service = _service(settings, embedder, overrides)
    arms: dict[str, Arm] = {}
    for name in arm_names:
        if name in PIPELINE_ARMS:
            variant = service.with_config(service.config.with_(**PIPELINE_ARMS[name]))
            arms[f"{name}{args.suffix}"] = PipelineArm(variant, f"{name}{args.suffix}")
        else:
            arms[name] = ARMS[name](settings, embedder)
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        results = {name: await run_arm(arm, items, factory) for name, arm in arms.items()}
    finally:
        await engine.dispose()
    ledger = corpus.load_ledger()
    fact_formats = {f["fact_id"]: f["source_type"] for f in ledger["facts"]}
    configs = {name: arm.config() for name, arm in arms.items()}
    run_info: dict[str, Any] = {
        "git": _git_sha(),
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config_hash": corpus.config_hash(
            {"arms": configs, "dataset": dataset.manifest.get("items_sha256")}
        ),
    }
    if args.milestone:
        run_info["milestone"] = args.milestone
    report = build_report(
        results,
        split=args.split,
        reference=args.reference or next(iter(arms)),
        fact_formats=fact_formats,
        manifest=dataset.manifest,
        arm_configs=configs,
        run_info=run_info,
    )
    write_report(report, args.out, args.title)
    if args.split == "test":
        with TEST_LOG.open("a", encoding="utf-8") as log:
            log.write(json.dumps({**run_info, "arms": arm_names, "out": str(args.out)}) + "\n")
    for name, arm in report["arms"].items():
        m = arm["metrics"]
        print(
            f"{name:28} hit@1 {m['hit@1']:.3f} hit@10 {m['hit@10']:.3f} "
            f"recall@10 {m['recall@10']:.3f} mrr {m['mrr']:.3f} "
            f"p50 {arm['latency_ms']['total_ms']['p50']}ms"
        )
    return 0


async def _profile(args: argparse.Namespace, settings: Settings) -> int:
    from sqlalchemy.ext.asyncio import create_async_engine

    from marketsignal.evaluation.profile import profile_lanes
    from marketsignal.evaluation.runner import _scopes

    items = select(load_frozen(args.dataset), "dev")
    embedder = _embedder_factory(settings)
    service = _service(settings, embedder, {"rerank": False, "balance": False})
    app_engine = create_engine(settings)
    su_engine = create_async_engine(args.superuser_dsn) if args.superuser_dsn else None
    try:
        from marketsignal.db.engine import create_session_factory as factory_of

        scopes = await _scopes(factory_of(app_engine), {i.workspace for i in items})
        await profile_lanes(service, items[:1], scopes, app_engine, su_engine)  # warm caches
        report = await profile_lanes(service, items, scopes, app_engine, su_engine)
    finally:
        await app_engine.dispose()
        if su_engine is not None:
            await su_engine.dispose()
    report["run"] = {"git": _git_sha(), "at": datetime.now(UTC).isoformat(timespec="seconds")}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "profile.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    lines = [
        "# Retrieval lanes under forced RLS (EXPLAIN ANALYZE)",
        "",
        f"- dev queries: {report['queries']} · git {report['run']['git']}",
        "",
        "| lane / role | n | exec p50 ms | exec p95 ms | GIN used | HNSW used "
        "| rows scanned p50 | max | indexes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, s in report["summary"].items():
        lines.append(
            f"| {key} | {s['n']} | {s['execution_ms_p50']} | {s['execution_ms_p95']} | "
            f"{s['gin_used']}/{s['n']} | {s['hnsw_used']}/{s['n']} | {s['rows_scanned_p50']} | "
            f"{s['rows_scanned_max']} | {', '.join(s['indexes']) or '-'} |"
        )
    (args.out / "profile.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


async def _reachability(args: argparse.Namespace, settings: Settings) -> int:
    """Which gold facts can a lane retrieve at all? A fact whose satisfying parents all have no
    children (purely numeric rows, ADR-0003 policy c2) is invisible to both lanes by design."""
    from sqlalchemy import text as sql

    from marketsignal.db.session import scoped_session
    from marketsignal.evaluation.runner import _scopes

    dataset = load_frozen(args.dataset)
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        scopes = await _scopes(factory, {i.workspace for i in dataset.items})
        with_children: set[str] = set()
        for scope in scopes.values():
            async with scoped_session(factory, scope) as session:
                rows = await session.execute(
                    sql(
                        "SELECT DISTINCT p.handle FROM parent_chunks p "
                        "JOIN child_chunks c ON c.parent_id = p.id"
                    )
                )
                with_children |= {r[0] for r in rows.all()}
    finally:
        await engine.dispose()
    out: dict[str, Any] = {"items": {}}
    for item in dataset.items:
        facts = {
            f.fact_id: any(h in with_children for h in f.handles()) for f in item.required_facts
        }
        out["items"][item.id] = {
            "split": item.split,
            "category": item.category,
            "facts": facts,
            "fully_reachable": all(facts.values()),
            "any_reachable": any(facts.values()),
        }
    for split in ("dev", "test"):
        members = [v for v in out["items"].values() if v["split"] == split]
        out[split] = {
            "items": len(members),
            "fully_reachable": sum(1 for v in members if v["fully_reachable"]),
            "unreachable_items": sorted(
                k for k, v in out["items"].items() if v["split"] == split and not v["any_reachable"]
            ),
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("dev", "test")}, indent=1))
    return 0


async def _seed(args: argparse.Namespace, settings: Settings) -> int:
    from marketsignal.evaluation.seed_local import seed_in_process

    result = await seed_in_process(settings)
    print(json.dumps(result))
    return 0 if not result["not_ready"] else 1


def _compare(args: argparse.Namespace) -> int:
    """Paired comparison of two arms recorded in (possibly) different results files."""
    from marketsignal.evaluation.metrics import ItemScore
    from marketsignal.evaluation.stats import mcnemar_exact, paired_bootstrap_diff

    def load(spec: str) -> tuple[str, dict[str, Any]]:
        path, _, arm = spec.rpartition(":")
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        return arm, report["arms"][arm]

    name_a, a = load(args.a)
    name_b, b = load(args.b)
    sa = {i["item_id"]: ItemScore(i["item_id"], i["fact_ranks"]) for i in a["items"]}
    sb = {i["item_id"]: ItemScore(i["item_id"], i["fact_ranks"]) for i in b["items"]}
    ids = sorted(sa.keys() & sb.keys())
    out: dict[str, Any] = {"a": args.a, "b": args.b, "n": len(ids)}
    for k in (1, 5, 10, 20):
        test = mcnemar_exact([sa[i].hit_at(k) for i in ids], [sb[i].hit_at(k) for i in ids])
        out[f"hit@{k}"] = {
            "only_a": test.only_a,
            "only_b": test.only_b,
            "p": round(test.p_value, 4),
        }
    for metric, fn in (
        ("mrr", lambda s: s.reciprocal_rank()),
        ("recall@10", lambda s: s.recall_at(10)),
    ):
        diff = paired_bootstrap_diff([fn(sa[i]) for i in ids], [fn(sb[i]) for i in ids])
        out[f"{metric}_diff_b_minus_a"] = diff.as_dict()
    out["changed_items"] = {
        i: {"a": dict(sa[i].fact_ranks), "b": dict(sb[i].fact_ranks)}
        for i in ids
        if sa[i].fact_ranks != sb[i].fact_ranks
    }
    out["latency_total_ms"] = {
        name_a: a["latency_ms"].get("total_ms"),
        name_b: b["latency_ms"].get("total_ms"),
    }
    text_out = json.dumps(out, indent=1)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text_out + "\n", encoding="utf-8")
    print(text_out)
    return 0


def _gate(args: argparse.Namespace) -> int:
    """Fail (exit 1) when an arm's metric falls below its floor in a results file."""
    report = json.loads(args.results.read_text(encoding="utf-8"))
    metrics = report["arms"][args.arm]["metrics"]
    failures = []
    for spec in args.min:
        name, _, floor = spec.partition("=")
        value = metrics[name]
        status = "ok" if value >= float(floor) else "FAIL"
        print(f"{status} {args.arm} {name} = {value:.3f} (floor {float(floor):.3f})")
        if status == "FAIL":
            failures.append(name)
    flags = report["arms"][args.arm].get("flags", {})
    if flags:
        print(f"FAIL degradation flags present: {flags}")
        failures.append("flags")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ms-eval")
    sub = parser.add_subparsers(dest="command", required=True)
    p_freeze = sub.add_parser("freeze")
    p_freeze.add_argument("--items", type=Path, default=DATASET_DIR / "items.json")
    p_freeze.add_argument("--out", type=Path, default=DATASET_DIR / "frozen.json")
    p_freeze.add_argument("--review", type=Path, default=DATASET_DIR / "alternates-review.json")
    p_int = sub.add_parser("integrity")
    p_int.add_argument("--dataset", type=Path, default=DATASET_DIR / "frozen.json")
    p_int.add_argument("--items", type=Path, default=DATASET_DIR / "items.json")
    p_run = sub.add_parser("run")
    p_run.add_argument("--dataset", type=Path, default=DATASET_DIR / "frozen.json")
    p_run.add_argument("--split", choices=("dev", "test"), default="dev")
    p_run.add_argument("--arms", required=True)
    p_run.add_argument("--reference")
    p_run.add_argument("--out", type=Path, required=True)
    p_run.add_argument("--title", default="Retrieval evaluation")
    p_run.add_argument("--milestone")
    p_run.add_argument("--set", action="append", help="RetrievalConfig override key=value")
    p_run.add_argument("--suffix", default="", help="appended to pipeline arm names")
    p_prof = sub.add_parser("profile")
    p_prof.add_argument("--dataset", type=Path, default=DATASET_DIR / "frozen.json")
    p_prof.add_argument("--superuser-dsn", help="control run without RLS (local dev only)")
    p_prof.add_argument("--out", type=Path, required=True)
    p_reach = sub.add_parser("reachability")
    p_reach.add_argument("--dataset", type=Path, default=DATASET_DIR / "frozen.json")
    p_reach.add_argument("--out", type=Path, required=True)
    sub.add_parser("seed")
    p_gate = sub.add_parser("gate")
    p_gate.add_argument("--results", type=Path, required=True)
    p_gate.add_argument("--arm", required=True)
    p_gate.add_argument("--min", action="append", required=True, help="metric=floor")
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("--a", required=True, help="results.json:arm")
    p_cmp.add_argument("--b", required=True, help="results.json:arm")
    p_cmp.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "gate":
        return _gate(args)
    if args.command == "compare":
        return _compare(args)
    settings = get_settings()
    handler = {
        "freeze": _freeze,
        "integrity": _integrity,
        "run": _run,
        "profile": _profile,
        "reachability": _reachability,
        "seed": _seed,
    }[args.command]
    return asyncio.run(handler(args, settings))
