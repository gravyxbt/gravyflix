"""Isolated bounded subprocess entrypoint; ffsubsync reports success as structured JSON."""
import json
import sys
from ffsubsync.ffsubsync import make_parser, run
result = run(make_parser().parse_args(sys.argv[1:]))
print(json.dumps(result))
