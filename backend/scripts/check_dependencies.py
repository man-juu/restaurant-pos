"""Check installed Python packages against PyPI's vulnerability data and yank status.

Standard library only, so the checker itself adds no supply-chain risk. PyPI's per-release
"vulnerabilities" come from the OSV database; a release that has been removed (often the fate
of malware) returns 404 and is reported too.

    pip freeze --exclude-editable > /tmp/req.txt
    python scripts/check_dependencies.py /tmp/req.txt
"""

import json
import sys
import urllib.error
import urllib.request


def main(path: str) -> int:
    pins = [line.strip().split("==") for line in open(path) if "==" in line]
    findings = 0
    for name, version in pins:
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            print(f"MISSING {name}=={version}: HTTP {exc.code} (removed from PyPI?)")
            findings += 1
            continue
        vulns = [v["id"] for v in data.get("vulnerabilities") or []]
        if vulns or data["info"].get("yanked"):
            print(f"{name}=={version}: yanked={data['info'].get('yanked')} vulns={vulns}")
            findings += 1
    print(f"Checked {len(pins)} packages: {findings} with findings.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
