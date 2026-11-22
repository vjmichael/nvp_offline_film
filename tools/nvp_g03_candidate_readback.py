"""Independent G03-M4 encrypted legacy candidate readback process.

Input is a single owner-supplied JSON document on stdin; the passphrase
MUST NEVER be passed as a command-line argument or logged. Output is a
hash-only recovery receipt, not the recovered screenplay or original media.

This verifies KNOWN original bytes but never authorizes migration cutover.
"""
from __future__ import annotations

import json
import sys

from backend.nvp_g03_candidate_recovery import reopen_known_originals


def main():
    request=json.load(sys.stdin)
    if not isinstance(request,dict) or set(request)!={
        "root","pid","passphrase","inventory"}:
        raise ValueError("Exact reviewed recovery request required")
    receipt=reopen_known_originals(
        request["root"],request["pid"],request["passphrase"],
        request["inventory"])
    print(json.dumps(receipt,sort_keys=True,separators=(",",":")))


if __name__=="__main__":
    main()
