"""Read-only developer probe for a local Lu 0.1.0-alpha.2 source checkout.

This DOES NOT start Lu, connect to a socket, borrow llama.cpp credentials,
change any model settings, run generation, or unload anyone's model.
"""
from __future__ import annotations

import argparse
import json
from backend.nvp_lu_alpha_contract import inspect_lu_alpha_source


def main():
    parser=argparse.ArgumentParser(description="NVP Lu alpha source/IPC compatibility gate")
    parser.add_argument("--lu-source",required=True,
        help="Local checkout matching the pinned Lu independent desktop source")
    args=parser.parse_args()
    result=inspect_lu_alpha_source(args.lu_source)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
