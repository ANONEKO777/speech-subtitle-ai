import argparse
import os
import shutil
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--stderr", type=Path)
parser.add_argument("--json", type=Path)
parser.add_argument("--exit", type=int, default=0)
parser.add_argument("--hang", type=float, default=0)
parser.add_argument("--pidfile", type=Path)
parser.add_argument("--argsfile", type=Path)
parser.add_argument("outputs", nargs="*", type=Path)
args = parser.parse_args()

if args.pidfile:
    args.pidfile.write_text(str(os.getpid()))
if args.argsfile:
    args.argsfile.write_text("\n".join(sys.argv[1:]), encoding="utf-8")
if args.stderr:
    for line in args.stderr.read_text(encoding="utf-8").splitlines():
        print(line, file=sys.stderr, flush=True)
        time.sleep(0.01)
if args.hang:
    time.sleep(args.hang)
if args.exit == 0 and args.json:
    for base in args.outputs:
        shutil.copyfile(args.json, base.with_name(base.name + ".json"))
sys.exit(args.exit)
