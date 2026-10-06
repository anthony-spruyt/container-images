"""Compose a flavor from the base linter set and the language definitions it lists."""

import re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined, select_autoescape

LANGUAGE_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_language(name: str, languages_dir: Path) -> dict:
    path = languages_dir / f"{name}.yaml"
    if not LANGUAGE_NAME.match(name) or not path.is_file():
        raise ValueError(
            f"Language {name!r} has no definition in {languages_dir} - "
            "add megalinter-factory/languages/<name>.yaml or fix the name."
        )
    return _load(path)


def _string_list(owner: str, field: str, value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(
            f"{owner}: {field} must be a list of names (linter keys or languages), got {value!r}"
        )
    return value


def resolve_languages(names: list[str], languages_dir: Path) -> list[tuple[str, dict]]:
    """
    Return every listed language plus the ones it includes, each once.

    Includes come before the language that includes them; otherwise by name.
    """
    seen: set[str] = set()
    ordered: list[tuple[str, dict]] = []

    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        language = _load_language(name, languages_dir)
        for include in sorted(_string_list(name, "languages", language.get("languages"))):
            visit(include)
        ordered.append((name, language))

    for name in sorted(names):
        visit(name)
    return ordered


def _render(fragment: str, **context: dict) -> str:
    # Autoescaping disabled: output is a Dockerfile, not HTML.
    env = Environment(
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        undefined=StrictUndefined,
    )
    return env.from_string(fragment).render(**context)


def compose_flavor(flavor: dict, factory_dir: Path) -> dict:
    """
    Merge the base set, the flavor's languages, and its own extras into one flavor.

    Linters are deduplicated and sorted so a compound flavor does not depend on
    the order its languages are listed in. Dockerfile fragments and test checks
    follow resolve_languages order, with the flavor's own last.
    """
    name = flavor.get("name", "flavor")
    base = _load(factory_dir / "base.yaml")
    languages = resolve_languages(
        _string_list(name, "languages", flavor.get("languages")), factory_dir / "languages"
    )

    linters = set(_string_list("base.yaml", "linters", base.get("linters")))
    fragments = []
    test_linters = []
    test_env_vars = []
    for language_name, language in languages:
        linters.update(_string_list(language_name, "linters", language.get("linters")))
        if language.get("extra_dockerfile"):
            fragments.append(_render(language["extra_dockerfile"], language=language))
        test_linters.extend(language.get("extra_test_linters", []))
        test_env_vars.extend(language.get("extra_test_env_vars", []))

    linters.update(_string_list(name, "custom_linters", flavor.get("custom_linters")))
    if flavor.get("extra_dockerfile"):
        fragments.append(_render(flavor["extra_dockerfile"], flavor=flavor))
    test_linters.extend(flavor.get("extra_test_linters", []))
    test_env_vars.extend(flavor.get("extra_test_env_vars", []))

    return {
        **flavor,
        "custom_linters": sorted(linters),
        "extra_dockerfile": "\n".join(fragments),
        "extra_test_linters": test_linters,
        "extra_test_env_vars": test_env_vars,
    }


def flavors_affected(changed_files: list[str], repo_root: Path) -> list[str]:
    """Return the flavor directories whose composition reads any of the changed files."""
    factory = "megalinter-factory"
    changed = set(changed_files)
    base_changed = f"{factory}/base.yaml" in changed
    affected = []
    for flavor_yaml in sorted(repo_root.glob("megalinter-*/flavor.yaml")):
        flavor = _load(flavor_yaml)
        names = _string_list(flavor_yaml.parent.name, "languages", flavor.get("languages"))
        used = resolve_languages(names, repo_root / factory / "languages")
        if base_changed or any(f"{factory}/languages/{name}.yaml" in changed for name, _ in used):
            affected.append(flavor_yaml.parent.name)
    return affected


def main() -> int:
    """Print the flavors affected by the changed files given as arguments, one per line."""
    for flavor_dir in flavors_affected(sys.argv[1:], Path(__file__).resolve().parent.parent):
        print(flavor_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
