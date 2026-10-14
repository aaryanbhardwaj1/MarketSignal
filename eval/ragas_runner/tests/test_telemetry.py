import os
import subprocess
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "ms_ragas_runner"


def test_importing_telemetry_disables_tracking_before_ragas_loads() -> None:
    env = {k: v for k, v in os.environ.items() if k != "RAGAS_DO_NOT_TRACK"}
    code = (
        "import sys\n"
        "import ms_ragas_runner.telemetry as t\n"
        "assert 'ragas' not in sys.modules\n"
        "import os\n"
        "assert os.environ['RAGAS_DO_NOT_TRACK'] == 'true'\n"
        "assert t.telemetry_disabled() is True\n"
        "print('ok')\n"
    )
    done = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"


def test_cli_entry_sets_flag_even_if_env_says_otherwise() -> None:
    env = {**os.environ, "RAGAS_DO_NOT_TRACK": "false"}
    code = (
        "import ms_ragas_runner.cli, ms_ragas_runner.telemetry as t; print(t.telemetry_disabled())"
    )
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "True"


def test_only_the_telemetry_module_imports_ragas() -> None:
    offenders = []
    for path in PACKAGE_DIR.glob("*.py"):
        if path.name == "telemetry.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "import ragas" in text or "from ragas" in text:
            offenders.append(path.name)
    assert offenders == []
