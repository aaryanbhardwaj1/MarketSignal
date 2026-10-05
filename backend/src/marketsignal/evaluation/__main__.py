import os
import sys

from marketsignal.evaluation.cli import main

code = main()
# The work is done and flushed; exit without interpreter teardown. On macOS, onnxruntime's static
# destructors can abort ("libc++abi ... recursive_mutex lock failed") during teardown after
# ingestion, turning a successful run into exit 134. os._exit skips that teardown.
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
