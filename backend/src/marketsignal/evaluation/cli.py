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
from marketsignal.evaluation.arms import Arm, BaselineDenseArm, BaselineLexicalArm
from marketsignal.evaluation.dataset import load_frozen, load_items, write_frozen
from marketsignal.evaluation.gold import freeze, integrity_problems
from marketsignal.evaluation.report import build_report, write_report
from marketsignal.evaluation.runner import run_arm, select
from marketsignal.providers.embeddings import Embedder, FastEmbedEmbedder

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
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown}; known: {sorted(ARMS)}", file=sys.stderr)
        return 2
    arms = {name: ARMS[name](settings, embedder) for name in arm_names}
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
        reference=args.reference or arm_names[0],
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
    args = parser.parse_args(argv)
    settings = get_settings()
    handler = {"freeze": _freeze, "integrity": _integrity, "run": _run}[args.command]
    return asyncio.run(handler(args, settings))
