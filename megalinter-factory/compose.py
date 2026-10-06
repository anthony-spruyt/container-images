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


def _load_language(name: str, option: str | None, languages_dir: Path) -> dict:
    path = languages_dir / f"{name}.yaml"
    if not LANGUAGE_NAME.match(name) or not path.is_file():
        raise ValueError(
            f"Language {name!r} has no definition in {languages_dir} - "
            "add megalinter-factory/languages/<name>.yaml or fix the name."
        )
    definition = _load(path)
    options = definition.pop("options", {})
    if option is None:
        return definition
    if option not in options:
        raise ValueError(
            f"Language {name!r} has no option {option!r}; options: {sorted(options) or 'none'}"
        )
    return options[option]


def _string_list(owner: str, field: str, value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(
            f"{owner}: {field} must be a list of names (linter keys or languages), got {value!r}"
        )
    return value


def _language_entries(owner: str, value: object) -> list[tuple[str, str | None]]:
    """Parse `languages`: each entry is `name`, or `{name: option}` to pick an option."""
    if value is None:
        return []
    entries = []
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, str):
                entries.append((entry, None))
            elif (
                isinstance(entry, dict)
                and len(entry) == 1
                and all(isinstance(v, str) for v in (*entry, *entry.values()))
            ):
                entries.append(next(iter(entry.items())))
            else:
                break
        else:
            return entries
    raise ValueError(
        f"{owner}: languages must be a list of language names or {{name: option}}, got {value!r}"
    )


def _entry_key(entry: tuple[str, str | None]) -> tuple[str, str]:
    return entry[0], entry[1] or ""


def resolve_languages(
    entries: list[tuple[str, str | None]], languages_dir: Path
) -> list[tuple[str, dict]]:
    """
    Return every listed language plus the ones it includes, each once.

    Includes come before the language that includes them; otherwise by name.
    """
    chosen: dict[str, str | None] = {}
    ordered: list[tuple[str, dict]] = []

    def visit(name: str, option: str | None) -> None:
        if name in chosen:
            if chosen[name] != option:
                raise ValueError(
                    f"Language {name!r} is used both as {chosen[name]!r} and {option!r}"
                )
            return
        chosen[name] = option
        language = _load_language(name, option, languages_dir)
        for include in sorted(_language_entries(name, language.get("languages")), key=_entry_key):
            visit(*include)
        ordered.append((name, language))

    for entry in sorted(entries, key=_entry_key):
        visit(*entry)
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
        _language_entries(name, flavor.get("languages")), factory_dir / "languages"
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
        entries = _language_entries(flavor_yaml.parent.name, flavor.get("languages"))
        used = resolve_languages(entries, repo_root / factory / "languages")
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
