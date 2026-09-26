"""Check bilingual page coverage and links in a built documentation site."""

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.duplicate_ids = set()
        self.links = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            if attrs["id"] in self.ids:
                self.duplicate_ids.add(attrs["id"])
            self.ids.add(attrs["id"])
        if tag == "a" and "name" in attrs:
            self.ids.add(attrs["name"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.links.append(attrs[key])


def check(root, site):
    errors = []
    source = root / "docs"
    english = {p.relative_to(source).as_posix() for p in source.rglob("*.md") if not p.name.endswith(".zh.md")}
    chinese = {p.relative_to(source).as_posix().removesuffix(".zh.md") + ".md" for p in source.rglob("*.zh.md")}
    for name in sorted(english ^ chinese):
        errors.append(f"Missing translation pair: {name}")
    if not english:
        errors.append("No source pages found")
    for name in sorted(english):
        suffix = Path(name).with_suffix("")
        output = suffix.parent / "index.html" if suffix.name == "index" else suffix / "index.html"
        for locale in ("", "zh"):
            if not (site / locale / output).is_file():
                errors.append(f"Missing built page: {locale}/{output}")
    pages = {p.resolve(): Page(p) for p in site.rglob("*.html")}
    prefix = urlsplit(os.environ.get("DOCS_SITE_URL", "http://127.0.0.1:8765/")).path.rstrip("/")
    checked = 0
    for path, page in pages.items():
        for ident in sorted(page.duplicate_ids):
            errors.append(f"Duplicate anchor: {path.relative_to(site)} -> #{ident}")
        for link in page.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            target_path = unquote(parsed.path)
            if not target_path:
                target = path
            elif target_path.startswith("/"):
                if prefix and (target_path == prefix or target_path.startswith(prefix + "/")):
                    target_path = target_path[len(prefix):]
                target = site / target_path.lstrip("/")
            else:
                target = path.parent / target_path
            target = target.resolve()
            if target.is_dir():
                target /= "index.html"
            label = f"{path.relative_to(site)} -> {link}"
            if not target.is_relative_to(site) or not target.is_file():
                errors.append("Broken link: " + label)
                continue
            fragment = unquote(parsed.fragment)
            if fragment and target in pages and fragment not in pages[target].ids:
                errors.append("Missing anchor: " + label)
            checked += 1
    index = site / "search/search_index.json"
    if not index.is_file():
        errors.append("Missing search index")
    else:
        entries = json.loads(index.read_text(encoding="utf-8")).get("docs", [])
        locations = [entry.get("location", "") for entry in entries]
        if not any(location.startswith("zh/") for location in locations):
            errors.append("Chinese pages absent from search index")
        if not any(not location.startswith("zh/") for location in locations):
            errors.append("English pages absent from search index")
    return errors, len(english), len(pages), checked


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=root / "site")
    args = parser.parse_args()
    errors, pairs, pages, links = check(root, args.site_dir.resolve())
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Documentation OK: {pairs} translation pairs, {pages} HTML files, {links} internal links.")


if __name__ == "__main__":
    main()
