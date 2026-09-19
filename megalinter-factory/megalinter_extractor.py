#!/usr/bin/env python3
"""
MegaLinter Descriptor Extractor

Extracts linter installation information directly from MegaLinter's descriptor files.
This ensures linter versions always match upstream MegaLinter without manual tracking.

Usage:
    from megalinter_extractor import get_megalinter_linters
    linters = get_megalinter_linters()
    print(linters["ACTION_ACTIONLINT"])
"""

import re
import shutil
import subprocess
from pathlib import Path

import yaml


def clone_megalinter(cache_dir: Path | None = None) -> Path:
    """
    Sparse clone MegaLinter repository to get descriptors only.

    Args:
        cache_dir: Directory to clone into. Defaults to ~/.cache/megalinter-factory

    Returns:
        Path to the descriptors directory
    """
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "megalinter-factory"
    cache_dir.mkdir(parents=True, exist_ok=True)

    ml_dir = cache_dir / "megalinter"

    # Always do a fresh clone for build reproducibility
    if ml_dir.exists():
        shutil.rmtree(ml_dir)

    subprocess.run(
        [
            "git",
            "clone",
            "--depth=1",
            "--filter=blob:none",
            "--sparse",
            "https://github.com/oxsecurity/megalinter.git",
            str(ml_dir),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(ml_dir),
            "sparse-checkout",
            "set",
            "megalinter/descriptors",
        ],
        check=True,
        capture_output=True,
    )

    return ml_dir / "megalinter" / "descriptors"


def parse_dockerfile_instructions(
    dockerfile_lines: list[str], linter_key: str
) -> dict[str, str | None]:
    """
    Parse ARG, FROM, COPY from dockerfile instructions for a specific linter.

    Args:
        dockerfile_lines: List of dockerfile instruction strings
        linter_key: The linter key to match (e.g., ACTION_ACTIONLINT)

    Returns:
        Dictionary with version, image, binary_path, target_path
    """
    result: dict[str, str | None] = {
        "version": None,
        "image": None,
        "binary_path": None,
        "target_path": None,
        "stage_name": None,
    }

    # Collect all ARG definitions
    args = {}
    # Track FROM stages
    stages = {}

    # Normalize linter key for matching (ACTION_ACTIONLINT -> actionlint)
    linter_name_lower = linter_key.split("_")[-1].lower().replace("-", "")

    for line in dockerfile_lines:
        if not line:
            continue

        # Handle multiline strings (from |- YAML)
        lines = line.strip().split("\n")
        for single_line in lines:
            single_line = single_line.strip()
            if not single_line or single_line.startswith("#"):
                continue

            # ARG ACTION_ACTIONLINT_VERSION=1.7.10
            if match := re.match(r"ARG\s+(\w+)=(.+)", single_line):
                arg_name = match.group(1)
                arg_value = match.group(2).strip()
                args[arg_name] = arg_value

            # FROM rhysd/actionlint:${ACTION_ACTIONLINT_VERSION} AS actionlint
            if match := re.match(
                r"FROM\s+([^:\s]+):(\S+)\s+AS\s+([\w-]+)", single_line, re.IGNORECASE
            ):
                stage_name = match.group(3).lower()
                stages[stage_name] = {
                    "image": match.group(1),
                    "version_ref": match.group(2),
                }

            # COPY --link --from=actionlint /usr/local/bin/actionlint /usr/bin/actionlint
            if match := re.search(
                r"COPY\s+.*--from=([\w-]+)\s+(\S+)\s+(\S+)", single_line, re.IGNORECASE
            ):
                stage_name = match.group(1).lower()
                # Match COPY that corresponds to this linter
                if stage_name == linter_name_lower or linter_name_lower in stage_name:
                    if result["binary_path"] is None:
                        result["binary_path"] = match.group(2)
                        result["target_path"] = match.group(3)
                        result["stage_name"] = stage_name

    # Find the matching stage for this linter
    matched_stage = None
    for stage_name, stage_info in stages.items():
        if stage_name == linter_name_lower or linter_name_lower in stage_name:
            matched_stage = stage_info
            result["stage_name"] = stage_name
            break

    if matched_stage:
        result["image"] = matched_stage["image"]
        version_ref = matched_stage["version_ref"]
        # Resolve version variable, preserving any prefix (e.g., "v" before ${VAR})
        if var_match := re.search(r"\$\{?(\w+)\}?", version_ref):
            var_name = var_match.group(1)
            if var_name in args:
                result["version"] = re.sub(
                    r"\$\{?" + re.escape(var_name) + r"\}?",
                    args[var_name],
                    version_ref,
                )
        else:
            result["version"] = version_ref

    # If no stage matched, try to find version from linter-specific ARG
    if result["version"] is None:
        for arg_name, arg_value in args.items():
            # Match ARG like ACTION_ACTIONLINT_VERSION or BASH_SHELLCHECK_VERSION
            if linter_key.replace("-", "_") in arg_name and "_VERSION" in arg_name:
                result["version"] = arg_value
                break

    return result


def load_shared_linters(descriptors_dir: Path) -> dict[str, dict]:
    """
    Load shared linter definitions referenced by descriptors via 'extends'.

    Args:
        descriptors_dir: Path to MegaLinter descriptors directory

    Returns:
        Dictionary mapping shared file stems (e.g. 'prettier') to their contents
    """
    shared = {}

    for shared_file in (descriptors_dir / "shared").glob("*.megalinter-linter.yml"):
        name = shared_file.name.removesuffix(".megalinter-linter.yml")
        shared[name] = yaml.safe_load(shared_file.read_text()) or {}

    return shared


def resolve_extends(linter: dict, shared_linters: dict[str, dict]) -> dict:
    """
    Merge a shared linter definition under a linter's own keys.

    Matches upstream precedence: the linter's own keys win over the shared ones.

    Args:
        linter: A linter entry from a descriptor's 'linters' list
        shared_linters: Lookup produced by load_shared_linters()

    Returns:
        The merged linter definition
    """
    base_name = linter.get("extends")
    if not base_name:
        return linter

    return {**shared_linters.get(base_name, {}), **linter}


def find_version_arg(dockerfile: list, prefix: str) -> str | None:
    """Return the first ARG <PREFIX>_*_VERSION value in dockerfile instructions."""
    for line in dockerfile:
        if match := re.search(rf"ARG\s+{prefix}_[\w_]+_VERSION=(\S+)", str(line)):
            return match.group(1)
    return None


def strip_npm_version(raw_package: str) -> str:
    """Strip the version suffix from an npm package spec, keeping any @scope/."""
    if "@${" in raw_package:
        return raw_package.split("@${")[0]
    # Scoped package like @scope/pkg@version - the leading @ is part of the name
    if raw_package.startswith("@") and raw_package.count("@") == 2:
        return raw_package.rsplit("@", 1)[0]
    if "@" in raw_package:
        return raw_package.split("@")[0]
    return raw_package


def strip_pip_version(raw_package: str) -> str:
    """Strip the version and any extras from a pip package spec."""
    if "@${" in raw_package:
        package = raw_package.split("@${")[0]
    elif "[" in raw_package:
        # Handle extras like "black[jupyter]@${VERSION}"
        package = raw_package.split("[")[0]
    else:
        package = raw_package.split("==")[0].split("@")[0]
    return package.split("[")[0]


def strip_gem_version(raw_package: str) -> str:
    """Strip the version from a gem package spec like "rubocop:${GEM_RUBOCOP_VERSION}"."""
    if ":${" in raw_package:
        return raw_package.split(":${")[0]
    if "@${" in raw_package:
        return raw_package.split("@${")[0]
    return raw_package.split(":")[0] if ":" in raw_package else raw_package


def detect_docker_binary(linter_info: dict, install: dict) -> dict | None:
    """Detect a linter installed by copying a binary out of another image."""
    dockerfile = install.get("dockerfile", [])
    if not dockerfile:
        return None

    df_info = parse_dockerfile_instructions(dockerfile, linter_info["linter_key"])
    if not (df_info["image"] and df_info["binary_path"]):
        return None

    return {
        "type": "docker_binary",
        "source_image": df_info["image"],
        "version": df_info["version"],
        "binary_path": df_info["binary_path"],
        "target_path": df_info["target_path"],
        "stage_name": df_info["stage_name"],
    }


def detect_npm(_linter_info: dict, install: dict) -> dict | None:
    """Detect an npm-installed linter and collect all of its packages."""
    packages = install.get("npm") or []
    if not packages:
        return None

    all_packages = [strip_npm_version(p) for p in packages]
    return {
        "type": "npm",
        "package": all_packages[0],  # Primary package
        "npm_packages": all_packages,
        "version": find_version_arg(install.get("dockerfile", []), "NPM"),
    }


def detect_pip(_linter_info: dict, install: dict) -> dict | None:
    """Detect a pip-installed linter."""
    packages = install.get("pip") or []
    if not packages:
        return None

    return {
        "type": "pip",
        "package": strip_pip_version(packages[0]),
        "version": find_version_arg(install.get("dockerfile", []), "PIP"),
    }


def detect_cargo(_linter_info: dict, install: dict) -> dict | None:
    """Detect a cargo-installed linter.

    MegaLinter does not pin cargo installs, so these take the rustup toolchain version.
    """
    packages = install.get("cargo") or []
    if not packages:
        return None

    return {"type": "cargo", "package": packages[0]}


def detect_gem(_linter_info: dict, install: dict) -> dict | None:
    """Detect a gem-installed linter."""
    packages = install.get("gem") or []
    if not packages:
        return None

    return {
        "type": "gem",
        "package": strip_gem_version(packages[0]),
        "version": find_version_arg(install.get("dockerfile", []), "GEM"),
    }


def detect_script(linter_info: dict, install: dict) -> dict | None:
    """Detect a linter installed by a wget/curl install script, such as Trivy."""
    dockerfile = install.get("dockerfile", [])
    if not dockerfile:
        return None

    dockerfile_text = "\n".join(str(line) for line in dockerfile)
    if not re.search(r"RUN\s+.*(?:wget|curl).*(?:install|\.sh)", dockerfile_text, re.IGNORECASE):
        return None

    # Try the most specific version ARG naming first, then fall back
    linter_name = linter_info["linter_name"].upper().replace("-", "_")
    patterns = [
        rf"ARG\s+{re.escape(linter_info['linter_key'])}_VERSION=(\S+)",
        rf"ARG\s+{re.escape(linter_name)}_VERSION=(\S+)",
        r"ARG\s+[\w_]+_VERSION=(\S+)",
    ]
    for pattern in patterns:
        if match := re.search(pattern, dockerfile_text):
            return {"type": "script", "version": match.group(1), "dockerfile": dockerfile}

    return None


def detect_apk(linter_info: dict, _install: dict) -> dict | None:
    """Detect a linter installed purely from Alpine packages."""
    return {"type": "apk"} if linter_info["apk_packages"] else None


def detect_dockerfile(_linter_info: dict, install: dict) -> dict | None:
    """Detect a linter set up by plain RUN instructions, such as bash-exec."""
    dockerfile = install.get("dockerfile", [])
    if not dockerfile:
        return None

    dockerfile_text = "\n".join(str(line) for line in dockerfile)
    if not re.search(r"^\s*RUN\s+", dockerfile_text, re.MULTILINE):
        return None

    return {"type": "dockerfile", "dockerfile": dockerfile}


# Ordered by precedence: the first detector to match wins.
INSTALL_DETECTORS = (
    detect_docker_binary,
    detect_npm,
    detect_pip,
    detect_cargo,
    detect_gem,
    detect_script,
    detect_apk,
    detect_dockerfile,
)


def build_linter_info(linter: dict, descriptor_id: str) -> dict:
    """
    Build the install info for a single linter entry.

    Args:
        linter: A linter entry, already merged with any shared definition
        descriptor_id: The owning descriptor's id, e.g. JAVASCRIPT

    Returns:
        Linter info dict; its "type" is None when no install method was detected
    """
    linter_name_raw = linter.get("linter_name", "")
    # Normalize: replace hyphens with underscores for consistency
    linter_name = linter_name_raw.upper().replace("-", "_")
    # 'name' is the actual key MegaLinter uses (e.g. JAVASCRIPT_ES); when absent
    # it is derived from the descriptor id and the linter name.
    linter_key = linter.get("name", f"{descriptor_id}_{linter_name}")

    install = linter.get("install", {})
    version_arg = linter.get("cli_version_arg_name", "--version")
    cli_name = linter_name_raw or linter_key.rsplit("_", maxsplit=1)[-1].lower()

    linter_info = {
        "linter_key": linter_key,
        "descriptor_id": descriptor_id,
        "linter_name": linter_name_raw,
        "cli_version_arg_name": version_arg,
        "version_command": f"{cli_name} {version_arg}",
        "type": None,
        "apk_packages": install.get("apk", []),  # Alpine package dependencies
    }

    for detector in INSTALL_DETECTORS:
        if detected := detector(linter_info, install):
            linter_info.update(detected)
            break

    return linter_info


def extract_linter_info(descriptors_dir: Path) -> dict:
    """
    Extract all linter info from MegaLinter descriptors.

    Args:
        descriptors_dir: Path to MegaLinter descriptors directory

    Returns:
        Dictionary mapping linter keys to their installation info
    """
    linters = {}
    shared_linters = load_shared_linters(descriptors_dir)

    for desc_file in descriptors_dir.glob("*.megalinter-descriptor.yml"):
        desc = yaml.safe_load(desc_file.read_text())
        descriptor_id = desc.get("descriptor_id", "").upper()

        for raw_linter in desc.get("linters", []):
            linter = resolve_extends(raw_linter, shared_linters)
            linter_info = build_linter_info(linter, descriptor_id)

            if linter_info["type"]:
                linters[linter_info["linter_key"]] = linter_info

    return linters


def extract_base_flavor_linters(descriptors_dir: Path) -> dict[str, list[str]]:
    """
    Extract which linters are included in each base MegaLinter flavor.

    Args:
        descriptors_dir: Path to MegaLinter descriptors directory

    Returns:
        Dictionary mapping flavor names to lists of linter keys
    """
    common_flavors = [
        "ci_light",
        "cupcake",
        "documentation",
        "dotnet",
        "dotnetweb",
        "go",
        "java",
        "javascript",
        "php",
        "python",
        "ruby",
        "rust",
        "salesforce",
        "security",
        "swift",
        "terraform",
        "formatters",
        "c_cpp",
    ]

    # Initialize flavor lists
    flavor_linters: dict[str, list[str]] = {flavor: [] for flavor in common_flavors}
    shared_linters = load_shared_linters(descriptors_dir)

    for desc_file in descriptors_dir.glob("*.megalinter-descriptor.yml"):
        desc = yaml.safe_load(desc_file.read_text())
        descriptor_id = desc.get("descriptor_id", "").upper()

        # Get descriptor-level flavors (applies to all linters unless overridden)
        descriptor_flavors = set(desc.get("descriptor_flavors", []))

        for raw_linter in desc.get("linters", []):
            linter = resolve_extends(raw_linter, shared_linters)
            # Use the 'name' field as the linter key (same as extract_linter_info)
            linter_name = linter.get("linter_name", "").upper().replace("-", "_")
            linter_key = linter.get("name", f"{descriptor_id}_{linter_name}")

            # Linter-level descriptor_flavors overrides descriptor-level if present
            linter_flavors = linter.get("descriptor_flavors")
            if linter_flavors is not None:
                effective_flavors = set(linter_flavors)
            else:
                effective_flavors = descriptor_flavors

            # Check if linter is in each flavor
            # Note: "all_flavors" is a flavor name (the full MegaLinter), not "all flavors"
            for flavor in common_flavors:
                if flavor in effective_flavors:
                    flavor_linters[flavor].append(linter_key)

    return flavor_linters


def get_megalinter_linters(cache_dir: Path | None = None) -> dict:
    """
    Main entry point: clone MegaLinter and extract all linter information.

    Args:
        cache_dir: Optional cache directory for cloned repo

    Returns:
        Dictionary with 'linters' and 'base_flavor_linters' keys
    """
    descriptors_dir = clone_megalinter(cache_dir)

    return {
        "linters": extract_linter_info(descriptors_dir),
        "base_flavor_linters": extract_base_flavor_linters(descriptors_dir),
    }


if __name__ == "__main__":
    # Test the extractor
    print("Extracting linter info from MegaLinter...")
    data = get_megalinter_linters()

    print(f"\nFound {len(data['linters'])} linters with install info:")
    for key, info in sorted(data["linters"].items()):
        if info["type"] == "docker_binary":
            print(f"  {key}: {info['source_image']}:{info['version']}")
        elif info["type"] in ("npm", "pip", "gem"):
            print(f"  {key}: {info['type']} {info['package']}@{info.get('version', 'latest')}")
        elif info["type"] == "cargo":
            print(f"  {key}: cargo {info['package']}")
        elif info["type"] == "script":
            print(f"  {key}: script v{info.get('version', 'unknown')}")
        elif info["type"] == "apk":
            print(f"  {key}: apk {info.get('apk_packages', [])}")
        elif info["type"] == "dockerfile":
            print(f"  {key}: dockerfile")

    print(f"\nBase flavors: {list(data['base_flavor_linters'].keys())}")
    print(f"ci_light has {len(data['base_flavor_linters'].get('ci_light', []))} linters")
