import json
import datetime
import re
from pathlib import Path

SRC = Path("robin_cookies.json")
DEST = Path("robin_cookies_selenium.json")

with SRC.open() as fh:
    raw = json.load(fh)

converted = []
for ck in raw:
    out = {
        "name": ck["Name"],
        "value": ck["Value"],
        "domain": ck["Domain"],
        "path": ck.get("Path", "/"),
    }
    # Secure / httpOnly
    out["secure"] = bool(ck.get("Secure"))
    if ck.get("HttpOnly") is not None:
        out["httpOnly"] = bool(ck["HttpOnly"])
    # SameSite, if present
    if "SameSite" in ck and ck["SameSite"]:
        out["sameSite"] = ck["SameSite"]
    # Expiry
    exp_raw = ck.get("Expires/Max-Age")
    if exp_raw and exp_raw not in ("Session", "", None):
        try:
            # ISO → epoch seconds (strip trailing “Z” first)
            dt = datetime.datetime.fromisoformat(re.sub(r"Z$", "", exp_raw))
            out["expiry"] = int(dt.timestamp())
        except ValueError:
            # if parse fails, skip expiry (cookie will be session-only)
            pass
    converted.append(out)

DEST.write_text(json.dumps(converted, indent=2))
print(f"Wrote {len(converted)} cookies to {DEST}")
