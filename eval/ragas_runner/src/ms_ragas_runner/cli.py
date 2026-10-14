"""``ragas-eval`` command line: ``offline`` (model-free) and ``llm`` (gated, model-judged)."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ms_ragas_runner import telemetry  # noqa: F401 - disables ragas tracking before anything else
from ms_ragas_runner.llm import (
    ACK_FLAG,
    DEFAULT_MODEL,
    DEFAULT_PRICE_INPUT_PER_MTOK,
    DEFAULT_PRICE_OUTPUT_PER_MTOK,
    GateError,
    run_llm,
)
from ms_ragas_runner.offline import run_offline
from ms_ragas_runner.results import OutputExistsError
from ms_ragas_runner.samples import SamplesError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ragas-eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--samples",
            type=Path,
            action="append",
            required=True,
            help="a marketsignal.ragas-samples JSON file (repeatable)",
        )
        p.add_argument(
            "--out", type=Path, required=True, help="output directory (must not exist yet)"
        )

    common(sub.add_parser("offline", help="score model-free RAGAS metrics (no model calls)"))
    live = sub.add_parser("llm", help="model-judged RAGAS metrics (gated; calls the model)")
    common(live)
    live.add_argument(ACK_FLAG, dest="acknowledged", action="store_true")
    live.add_argument("--confirm-cost", action="store_true", help="actually make the calls")
    live.add_argument("--model", default=DEFAULT_MODEL)
    live.add_argument(
        "--price-input-per-mtok",
        type=float,
        default=DEFAULT_PRICE_INPUT_PER_MTOK,
        help="USD per million input tokens for the estimate (default: %(default)s)",
    )
    live.add_argument(
        "--price-output-per-mtok",
        type=float,
        default=DEFAULT_PRICE_OUTPUT_PER_MTOK,
        help="USD per million output tokens for the estimate (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "offline":
            results = run_offline(args.samples, args.out)
            for run in results["runs"]:
                print(f"{run['run_id']}/{run['configuration']}: n={run['n_samples']}")
            print(f"wrote {args.out}/results.json and report.md")
            return 0
        return run_llm(
            args.samples,
            args.out,
            acknowledged=args.acknowledged,
            confirm_cost=args.confirm_cost,
            model=args.model,
            price_input_per_mtok=args.price_input_per_mtok,
            price_output_per_mtok=args.price_output_per_mtok,
        )
    except (GateError, OutputExistsError, SamplesError, ValueError) as exc:
        print(f"ragas-eval: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
