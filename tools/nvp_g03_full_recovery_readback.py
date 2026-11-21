"""Separate-process original-film SQLite/FilmIndex recovery (stdin-only credential)."""
from __future__ import annotations
import json
import sys
from backend.nvp_g03_full_recovery import reconstruct_and_reopen

def main():
    request=json.load(sys.stdin)
    if not isinstance(request,dict) or set(request)!={"root","pid","passphrase","inventory"}:
        raise ValueError("Exact reviewed historical-film recovery request required")
    receipt=reconstruct_and_reopen(request["root"],request["pid"],
                                  request["passphrase"],request["inventory"])
    print(json.dumps(receipt,sort_keys=True,separators=(",",":")))

if __name__=="__main__":
    main()
