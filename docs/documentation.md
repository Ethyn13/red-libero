# Build and maintain the documentation

The site uses [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) and [mkdocs-static-i18n](https://ultrabug.github.io/mkdocs-static-i18n/). It is built from Markdown and served as static files. No simulator, GPU, or model weights are required.

<h2 id="contents">Table of Contents</h2>

1. [One-time setup](#one-time-setup)
2. [Preview locally](#preview-locally)
3. [Build and check](#build-and-check)
4. [Write a bilingual page](#write-a-bilingual-page)
5. [Keep reference data current](#keep-reference-data-current)
6. [Publish the static output](#publish-the-static-output)

---

<a id="one-time-setup"></a>

## 1. One-time setup

Run from the red-libero root:

```bash
conda env create -f environment-docs.yml
conda activate red-libero-docs
```

The [docs environment](downloads/environment-docs.yml) uses Python 3.11. [requirements/docs.txt](downloads/requirements/docs.txt) pins MkDocs 1.6.1, Material 9.7.7, static-i18n 1.3.1, and jieba 0.42.1 for Chinese search segmentation. It is independent of the simulation environment.

<a id="preview-locally"></a>

## 2. Preview locally

```bash
python -m mkdocs serve -a 127.0.0.1:8765
```

Open `http://127.0.0.1:8765/` for English or `/zh/` for Chinese. Keep the command running while editing. For a remote host, use the SSH forwarding instructions in [remote access](remote.md).

<a id="build-and-check"></a>

## 3. Build and check

```bash
python -m mkdocs build --strict
python scripts/check_docs.py
```

The static site is written to `site/`, which is ignored by Git. The checker verifies translation pairs and internal HTML links / anchors. The docs workflow runs the same build and checks, then uploads the static site as a build artifact. It does not publish it automatically.

<a id="write-a-bilingual-page"></a>

## 4. Write a bilingual page

Use suffix pairs in `docs/`:

```text
docs/
├── quickstart.md       # English
├── quickstart.zh.md    # Chinese
├── assets/
└── images/
```

Add the English path to `nav` in `mkdocs.yml`, then add its Chinese label under `nav_translations`. Write links using the English source filename in both languages, such as `[Rules](SAFETY_RULES.md)`; the localization plugin resolves the corresponding page.

Use English for commands, paths, configuration keys, predicate names, and GUI labels. Translate explanations. Prefer descriptive headings, short procedures, and concrete examples. The main source files and GUI remain English.

Use the guide format consistently: a title and short introduction, an explicit table of contents, numbered sections (`1.`, `2.`), numbered subsections (`1.1`, `1.2`), command examples, parameter tables, and blockquote notes. Keep the Markdown readable in the repository as well as the website. Add the page to the documentation overview and preserve existing anchor IDs when renaming a heading.

<a id="keep-reference-data-current"></a>

## 5. Keep reference data current

`docs/hooks.py` creates downloadable configuration files from the authoritative repository files at build time. It also generates the predicate tables from `gui_modules/safety/catalog.py`, without importing the simulator. Chinese predicate descriptions live in `docs/assets/predicates.zh.json`. Build failure identifies missing translations.

The style, icon, fonts, and search assets are bundled locally. The site does not need a hosted search provider or external font service.

<a id="publish-the-static-output"></a>

## 6. Publish the static output

Before a public build, set `DOCS_SITE_URL` to the final URL, including any path prefix and trailing slash:

```bash
export DOCS_SITE_URL=https://your-organization.github.io/your-repository/
python -m mkdocs build --strict
python scripts/check_docs.py
```

Upload the contents of `site/` to the selected static host, or use your repository's GitHub Pages deployment process. Serve the files over HTTP(S), preserving directory URLs and the `zh/` subtree. Do not open `index.html` directly with a `file://` URL when checking search.

The default site URL is a local preview address. Setting a URL in the build configuration does not publish the site or configure a domain. [redvla.github.io](https://redvla.github.io) is the project website; choose the documentation's deployment destination separately.
