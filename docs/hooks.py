"""Build reference material from authoritative repository files."""

import json
from pathlib import Path
import runpy
from mkdocs.structure.files import File


def on_files(files, config):
    root = Path(config.config_file_path).parent
    sources = ["environment.yml", "environment-docs.yml", "requirements/studio.txt",
               "requirements/docs.txt", "LICENSE", "NOTICE.md", "CITATION.cff", "configs/safety/cumulative.bddl"]
    sources.extend(f"configs/policies/{name}.yaml" for name in ("openvla", "vla-adapter", "pi0", "custom-script"))
    for source in sources:
        destination = "downloads/" + source
        if source.endswith(".md"):
            destination = destination.removesuffix(".md") + ".txt"
        files.append(File.generated(config, destination, abs_src_path=str(root / source)))
    return files


def on_page_markdown(markdown, page, config, files):
    if "<!-- predicate-catalog:" not in markdown:
        return markdown
    root = Path(config.config_file_path).parent
    predicates = runpy.run_path(str(root / "gui_modules/safety/catalog.py"))["PREDICATES"]
    translations = json.loads((root / "docs/assets/predicates.zh.json").read_text(encoding="utf-8"))
    if set(translations) != set(predicates):
        missing = sorted(set(predicates) - set(translations))
        extra = sorted(set(translations) - set(predicates))
        raise ValueError(f"Predicate translations out of sync: missing={missing}, extra={extra}")
    for language in ("en", "zh"):
        marker = f"<!-- predicate-catalog:{language} -->"
        if marker not in markdown:
            continue
        heading = "| Predicate | Signatures | Description |" if language == "en" else "| 谓词 | 参数签名 | 说明 |"
        rows = [heading, "| --- | --- | --- |"]
        for name, spec in predicates.items():
            signatures = "<br>".join(f"`({name}{(' ' + ' '.join(args)) if args else ''})`" for args in spec.signatures)
            description = spec.description if language == "en" else translations[name]
            rows.append(f"| `{name}` | {signatures} | {description.replace('|', '&#124;')} |")
        markdown = markdown.replace(marker, "\n".join(rows))
    return markdown
