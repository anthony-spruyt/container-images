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
        import shutil

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
                r"FROM\s+([^:\s]+):(\S+)\s+AS\s+(\w+)", single_line, re.IGNORECASE
            ):
                stage_name = match.group(3).lower()
                stages[stage_name] = {
                    "image": match.group(1),
                    "version_ref": match.group(2),
                }

            # COPY --link --from=actionlint /usr/local/bin/actionlint /usr/bin/actionlint
            if match := re.search(
                r"COPY\s+.*--from=(\w+)\s+(\S+)\s+(\S+)", single_line, re.IGNORECASE
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
        # Resolve version variable
        if var_match := re.match(r"\$\{?(\w+)\}?", version_ref):
            var_name = var_match.group(1)
            if var_name in args:
                result["version"] = args[var_name]
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


def extract_linter_info(descriptors_dir: Path) -> dict:
    """
    Extract all linter info from MegaLinter descriptors.

    Args:
        descriptors_dir: Path to MegaLinter descriptors directory

    Returns:
        Dictionary mapping linter keys to their installation info
    """
    linters = {}

    for desc_file in descriptors_dir.glob("*.megalinter-descriptor.yml"):
        desc = yaml.safe_load(desc_file.read_text())

        for linter in desc.get("linters", []):
            # Build linter key: DESCRIPTOR_LINTERNAME (e.g., ACTION_ACTIONLINT)
            descriptor_id = desc.get("descriptor_id", "").upper()
            linter_name_raw = linter.get("linter_name", "")
            # Normalize: replace hyphens with underscores for consistency
            linter_name = linter_name_raw.upper().replace("-", "_")
            linter_key = f"{descriptor_id}_{linter_name}"

            install = linter.get("install", {})
            dockerfile = install.get("dockerfile", [])

            linter_info = {
                "linter_key": linter_key,
                "descriptor_id": descriptor_id,
                "linter_name": linter_name_raw,
                "cli_version_arg_name": linter.get("cli_version_arg_name", "--version"),
                "version_command": None,
                "type": None,
            }

            # Build version command
            cli_name = linter_name_raw or linter_key.split("_")[-1].lower()
            version_arg = linter.get("cli_version_arg_name", "--version")
            linter_info["version_command"] = f"{cli_name} {version_arg}"

            # Handle dockerfile-based installation (docker_binary type)
            if dockerfile:
                info = parse_dockerfile_instructions(dockerfile, linter_key)
                if info["image"] and info["binary_path"]:
                    linter_info["type"] = "docker_binary"
                    linter_info["source_image"] = info["image"]
                    linter_info["version"] = info["version"]
                    linter_info["binary_path"] = info["binary_path"]
                    linter_info["target_path"] = info["target_path"]
                    linter_info["stage_name"] = info["stage_name"]

            # Handle npm installation (only if not already docker_binary)
            if "npm" in install and linter_info["type"] is None:
                npm_packages = install["npm"]
                if npm_packages:
                    # Extract package name - handle formats like:
                    # - "markdownlint-cli@${NPM_MARKDOWNLINT_CLI_VERSION}"
                    # - "@stoplight/spectral-cli@${NPM_SPECTRAL_VERSION}"
                    raw_package = npm_packages[0]
                    # Split on @$ to get package name (handles scoped packages)
                    if "@${" in raw_package:
                        package = raw_package.split("@${")[0]
                    elif raw_package.startswith("@") and raw_package.count("@") == 2:
                        # Scoped package like @scope/pkg@version
                        parts = raw_package.rsplit("@", 1)
                        package = parts[0]
                    else:
                        package = raw_package.split("@")[0] if "@" in raw_package else raw_package

                    linter_info["type"] = "npm"
                    linter_info["package"] = package
                    # Find version from dockerfile ARGs
                    if dockerfile:
                        for line in dockerfile:
                            if match := re.search(
                                r"ARG\s+NPM_[\w_]+_VERSION=(\S+)", str(line)
                            ):
                                linter_info["version"] = match.group(1)
                                break

            # Handle pip installation (only if not already set)
            if "pip" in install and linter_info["type"] is None:
                pip_packages = install["pip"]
                if pip_packages:
                    # Handle formats like "bandit@${PIP_BANDIT_VERSION}"
                    raw_package = pip_packages[0]
                    if "@${" in raw_package:
                        package = raw_package.split("@${")[0]
                    elif "[" in raw_package:
                        # Handle extras like "black[jupyter]@${VERSION}"
                        package = raw_package.split("[")[0]
                    else:
                        package = raw_package.split("==")[0].split("@")[0]
                    # Remove extras bracket if present
                    package = package.split("[")[0]

                    linter_info["type"] = "pip"
                    linter_info["package"] = package
                    if dockerfile:
                        for line in dockerfile:
                            if match := re.search(
                                r"ARG\s+PIP_[\w_]+_VERSION=(\S+)", str(line)
                            ):
                                linter_info["version"] = match.group(1)
                                break

            # Store linter info if we have a type
            if linter_info["type"]:
                linters[linter_key] = linter_info

    return linters


def extract_base_flavor_linters(descriptors_dir: Path) -> dict[str, list[str]]:
    """
    Extract which linters are included in each base MegaLinter flavor.

    Args:
        descriptors_dir: Path to MegaLinter descriptors directory

    Returns:
        Dictionary mapping flavor names to lists of linter keys
    """
    # Read the all_flavors.json or infer from linter disabled_in_flavor fields
    flavor_linters = {}

    for desc_file in descriptors_dir.glob("*.megalinter-descriptor.yml"):
        desc = yaml.safe_load(desc_file.read_text())
        descriptor_id = desc.get("descriptor_id", "").upper()

        for linter in desc.get("linters", []):
            linter_name = linter.get("linter_name", "").upper()
            linter_key = f"{descriptor_id}_{linter_name}"

            # Linters can specify which flavors they're disabled in
            disabled_in = set(linter.get("disabled_in_flavor", []))
            # Or which flavors they're enabled in (descriptor level)
            install_details = linter.get("install", {})
            only_in_flavors = install_details.get("only_in_flavor", [])

            # For simplicity, we'll track common flavors
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

            for flavor in common_flavors:
                if flavor not in flavor_linters:
                    flavor_linters[flavor] = []

                # Add linter to flavor if not disabled
                if flavor not in disabled_in:
                    if not only_in_flavors or flavor in only_in_flavors:
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
        elif info["type"] in ("npm", "pip"):
            print(f"  {key}: {info['type']} {info['package']}@{info.get('version', 'latest')}")

    print(f"\nBase flavors: {list(data['base_flavor_linters'].keys())}")
    print(f"ci_light has {len(data['base_flavor_linters'].get('ci_light', []))} linters")
