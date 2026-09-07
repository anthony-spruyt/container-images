"""Regenerate megalinter-factory/requirements.txt with sha256 wheel hashes.

Run after bumping a version in PKGS:

    python megalinter-factory/gen_requirements_hashes.py
"""

import json
import pathlib
import urllib.request

# markupsafe is a jinja2 dependency; --require-hashes needs every transitive one.
PKGS = {"jinja2": "3.1.6", "markupsafe": "3.0.3", "pyyaml": "6.0.3"}

REQUIREMENTS = pathlib.Path(__file__).with_name("requirements.txt")

HEADER = """# Pinned with hashes so only these exact wheels can be installed.
# Regenerate after a version bump:
#   python megalinter-factory/gen_requirements_hashes.py
# markupsafe is a jinja2 dependency and must be listed for --require-hashes.
"""


def is_supported_wheel(filename: str) -> bool:
    """Return True for wheels a linux x86_64 GitHub runner can install."""
    if not filename.endswith(".whl"):
        return False
    if filename.endswith("-py3-none-any.whl"):
        return True
    return "manylinux" in filename and "x86_64" in filename and "cp3" in filename


def wheel_hashes(name: str, version: str) -> list[str]:
    """Fetch sorted sha256 digests of the supported wheels for a release."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        release = json.load(response)

    digests = sorted(
        {
            item["digests"]["sha256"]
            for item in release["urls"]
            if is_supported_wheel(item["filename"])
        }
    )
    if not digests:
        raise SystemExit(f"No supported wheels found for {name} {version}")
    return digests


def main() -> None:
    """Write requirements.txt with a pinned, hashed entry per package."""
    entries = []
    for name, version in PKGS.items():
        digests = wheel_hashes(name, version)
        hashes = " \\\n".join(f"    --hash=sha256:{d}" for d in digests)
        entries.append(f"{name}=={version} \\\n{hashes}")
        print(f"{name}=={version}: {len(digests)} wheel hashes")

    REQUIREMENTS.write_text(HEADER + "\n".join(entries) + "\n", encoding="utf-8")
    print(f"Wrote {REQUIREMENTS}")


if __name__ == "__main__":
    main()
