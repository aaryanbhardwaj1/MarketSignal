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


async def _index_state(settings: Settings, codes: set[str]) -> dict[str, Any]:
    from marketsignal.evaluation.gold import index_state, load_workspace

    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        workspaces = {code: await load_workspace(factory, code) for code in sorted(codes)}
        return await index_state(factory, workspaces)
    finally:
        await engine.dispose()


def _reference(name: str | None, suffix: str, arms: dict[str, Arm]) -> str:
    """The reference arm; a pipeline arm name given without the run's --suffix gets it added."""
    if name is None:
        return next(iter(arms))
    if name not in arms and f"{name}{suffix}" in arms:
        return f"{name}{suffix}"
    if name not in arms:
        raise SystemExit(f"reference arm {name!r} is not among {sorted(arms)}")
    return name


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
    index = await _index_state(settings, {i.workspace for i in items})
    run_info: dict[str, Any] = {
        "git": _git_sha(),
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "index": index,  # what was actually queried (pipeline versions of active versions)
        "config_hash": corpus.config_hash(
            {"arms": configs, "dataset": dataset.manifest.get("items_sha256"), "index": index}
        ),
    }
    if args.milestone:
        run_info["milestone"] = args.milestone
    from marketsignal.evaluation.task_types import load_task_types

    report = build_report(
        results,
        task_types=load_task_types(args.dataset.parent / "task-types.json"),
        split=args.split,
        reference=_reference(args.reference, args.suffix, arms),
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

    if args.split == "test" and not args.milestone:
        print("refusing to inspect the frozen test split without --milestone", file=sys.stderr)
        return 2
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
    out: dict[str, Any] = {"split": args.split, "items": {}}
    for item in dataset.split(args.split):
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
    members = list(out["items"].values())
    out["summary"] = {
        "items": len(members),
        "fully_reachable": sum(1 for v in members if v["fully_reachable"]),
        "unreachable_items": sorted(k for k, v in out["items"].items() if not v["any_reachable"]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    if args.split == "test":
        with TEST_LOG.open("a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {
                        "git": _git_sha(),
                        "at": datetime.now(UTC).isoformat(timespec="seconds"),
                        "command": "reachability",
                        "milestone": args.milestone,
                        "out": str(args.out),
                    }
                )
                + "\n"
            )
    print(json.dumps(out["summary"], indent=1))
    return 0


async def _classify(args: argparse.Namespace, settings: Settings) -> int:
    """Write task-types.json beside the frozen dataset (structural rule, logged: covers test)."""
    from marketsignal.evaluation.task_types import classify

    dataset = load_frozen(args.dataset)
    engine = create_engine(settings)
    try:
        result = await classify(dataset, create_session_factory(engine))
    finally:
        await engine.dispose()
    out = args.dataset.parent / "task-types.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    with TEST_LOG.open("a", encoding="utf-8") as log:
        entry = {"git": _git_sha(), "at": datetime.now(UTC).isoformat(timespec="seconds")}
        log.write(json.dumps({**entry, "command": "classify", "milestone": args.milestone}) + "\n")
    print(json.dumps(result["composition"]))
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
    report_a = json.loads(Path(args.a.rpartition(":")[0]).read_text(encoding="utf-8"))
    report_b = json.loads(Path(args.b.rpartition(":")[0]).read_text(encoding="utf-8"))
    if report_a["split"] != report_b["split"] or (
        report_a["dataset"].get("items_sha256") != report_b["dataset"].get("items_sha256")
    ):
        print("refusing to compare runs over different splits or datasets", file=sys.stderr)
        return 2
    ids = sorted(sa.keys() & sb.keys())
    if not ids or len(ids) != len(sa) or len(ids) != len(sb):
        print(
            f"refusing: item sets differ ({len(sa)} vs {len(sb)}, {len(ids)} shared)",
            file=sys.stderr,
        )
        return 2
    out: dict[str, Any] = {"a": args.a, "b": args.b, "n": len(ids)}
    for k in (1, 5, 10, 20):
        test = mcnemar_exact([sa[i].hit_at(k) for i in ids], [sb[i].hit_at(k) for i in ids])
        out[f"hit@{k}"] = {
            "only_a": test.only_a,
            "only_b": test.only_b,
            "p": round(test.p_value, 4),
        }

    def mrr(s: ItemScore) -> float:
        return s.reciprocal_rank()

    def recall10(s: ItemScore) -> float:
        return s.recall_at(10)

    for metric, fn in (("mrr", mrr), ("recall@10", recall10)):
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
    """Fail (exit 1) when an arm's metric falls below its floor in a results file. With
    ``--task-type retrieval`` the floors apply to the retrieval-eligible summary."""
    report = json.loads(args.results.read_text(encoding="utf-8"))
    arm_report = report["arms"][args.arm]
    if args.task_type:
        if "retrieval_eligible" not in arm_report:
            print("no retrieval-eligible summary in this results file", file=sys.stderr)
            return 2
        metrics = arm_report["retrieval_eligible"]["metrics"]
        print(f"gate over retrieval-eligible items (n={metrics['n']})")
    else:
        metrics = arm_report["metrics"]
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


FAKE_ANSWER = (
    "### Answer\nThe evidence addresses this question [E1].\n\n### Key findings\n- The most "
    "relevant evidence item is cited here [E1].\n\n### Gaps & unknowns\nThe offline fake "
    "model does not read the evidence.\n"
)


async def _grounded(args: argparse.Namespace, settings: Settings) -> int:
    """Grounded-answer evaluation through the real in-process API (live model by default).

    ``--mode`` absent: requests carry no mode (backwards compatible); ``standard``/``research``/
    ``auto``: every request carries that mode; ``both``: every item runs standard then research
    and the paired comparison is written (results-standard.json, results-research.json,
    compare.json, report.md)."""
    from marketsignal.api.app import create_app
    from marketsignal.evaluation.grounded import evaluate_modes, select_items
    from marketsignal.evaluation.grounded_compare import compare
    from marketsignal.evaluation.grounded_report import MODES, render, render_comparison
    from marketsignal.evaluation.grounded_stats import Prices

    dataset = json.loads(args.items.read_text(encoding="utf-8"))["items"]
    items = select_items(dataset, split=args.split, ids=args.ids, limit=args.limit)
    # The empty-pack gate is required only for datasets that contain empty-pack items.
    require_empty_pack = any(i["expect"] == "abstain_no_llm" for i in dataset)
    if not args.fake and settings.anthropic_api_key is None:
        print(
            "ANTHROPIC_API_KEY is not configured (use --fake for an offline run)", file=sys.stderr
        )
        return 2
    app = create_app(settings)
    if args.fake:
        from marketsignal.providers.llm.fake import FakeLLM

        fake = FakeLLM([FAKE_ANSWER], repeat_last=True)
        app.state.llm_provider = lambda: fake
    prices = (
        Prices(0.0, 0.0, 0.0, 0.0)
        if args.fake
        else Prices(
            input=settings.llm_price_input_per_mtok,
            output=settings.llm_price_output_per_mtok,
            cache_write=settings.llm_price_cache_write_per_mtok,
            cache_read=settings.llm_price_cache_read_per_mtok,
        )
    )
    modes: tuple[str | None, ...] = MODES if args.mode == "both" else (args.mode,)
    results = await evaluate_modes(
        app,
        items,
        modes,
        concurrency=args.concurrency,
        prices=prices,
        require_empty_pack=require_empty_pack,
    )
    meta = {
        "git": _git_sha(),
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": "fake-llm" if args.fake else settings.llm_model,
        "effort": settings.llm_effort,
        "thinking": settings.llm_thinking,
        "retrieval_config_hash": app.state.retrieval_service.config_hash,
        "dataset": str(args.items),
        "split": args.split,
        "items": len(items),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    for key, result in results.items():
        result["run"] = {**meta, "mode": None if key == "default" else key}
        name = "results.json" if len(results) == 1 else f"results-{key}.json"
        (args.out / name).write_text(json.dumps(result, indent=1, default=str) + "\n")
    if args.mode == "both":
        cmp = compare(results["standard"]["items"], results["research"]["items"])
        (args.out / "compare.json").write_text(json.dumps(cmp, indent=1, default=str) + "\n")
        (args.out / "report.md").write_text(render_comparison(cmp, results, run=meta))
    else:
        (args.out / "report.md").write_text(render(next(iter(results.values()))))
    ok = True
    for key, result in results.items():
        for name, gate in result["summary"]["hard_gates"].items():
            ok = ok and gate["pass"]
            print(f"{'ok  ' if gate['pass'] else 'FAIL'} [{key}] {name}: {gate['value']}")
    return 0 if ok else 1


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
    p_reach.add_argument("--split", choices=("dev", "test"), default="dev")
    p_reach.add_argument("--milestone")
    sub.add_parser("seed")
    p_gate = sub.add_parser("gate")
    p_gate.add_argument("--results", type=Path, required=True)
    p_gate.add_argument("--arm", required=True)
    p_gate.add_argument("--min", action="append", required=True, help="metric=floor")
    p_gate.add_argument("--task-type", choices=("retrieval",))
    p_cls = sub.add_parser("classify")
    p_cls.add_argument("--dataset", type=Path, default=DATASET_DIR / "frozen.json")
    p_cls.add_argument("--milestone", required=True, help="covers the test split: logged")
    p_g = sub.add_parser("grounded")
    p_g.add_argument(
        "--items", type=Path, default=corpus.EVAL_DIR / "datasets" / "grounded-v0" / "items.json"
    )
    p_g.add_argument("--out", type=Path, required=True)
    p_g.add_argument("--split", choices=("dev", "test", "all"), default="all")
    p_g.add_argument(
        "--mode",
        choices=("standard", "research", "auto", "both"),
        help="request mode (absent: no mode field); both = paired standard vs research",
    )
    p_g.add_argument("--fake", action="store_true", help="offline plumbing run with FakeLLM")
    p_g.add_argument("--ids")
    p_g.add_argument("--limit", type=int)
    p_g.add_argument("--concurrency", type=int, default=1)
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
        "classify": _classify,
        "grounded": _grounded,
    }[args.command]
    return asyncio.run(handler(args, settings))
