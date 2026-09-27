# 构建与维护文档站

文档站基于 [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) 和 [mkdocs-static-i18n](https://ultrabug.github.io/mkdocs-static-i18n/)，从 Markdown 构建为静态网页。构建不需要仿真器、GPU 或模型权重。

<h2 id="contents">目录</h2>

1. [首次配置](#_2)
2. [本地预览](#_3)
3. [构建与检查](#_4)
4. [添加双语页面](#_5)
5. [避免参考内容过期](#_6)
6. [使用 GitHub Pages 发布](#_7)

---

<a id="_2"></a>

## 1. 首次配置

在 red-libero 根目录执行：

```bash
conda env create -f environment-docs.yml
conda activate red-libero-docs
```

[文档环境](downloads/environment-docs.yml)使用 Python 3.11。[requirements/docs.txt](downloads/requirements/docs.txt)锁定 MkDocs 1.6.1、Material 9.7.7、static-i18n 1.3.1，以及用于中文搜索分词的 jieba 0.42.1。它与仿真环境相互独立。

<a id="_3"></a>

## 2. 本地预览

```bash
python -m mkdocs serve -a 127.0.0.1:8765
```

访问 `http://127.0.0.1:8765/` 查看英文，访问 `/zh/` 查看中文。编辑时保持进程运行。远程服务器预览使用[远程访问](remote.md)中的 SSH 转发方式。

<a id="_4"></a>

## 3. 构建与检查

```bash
python -m mkdocs build --strict
python scripts/check_docs.py
```

静态页面输出到 `site/`，该目录被 Git 忽略。检查脚本校验双语页面配对及内部 HTML 链接和锚点。文档工作流执行相同的构建与检查，然后上传网页构建产物；主分支通过检查后自动部署到 GitHub Pages。

<a id="_5"></a>

## 4. 添加双语页面

在 `docs/` 下使用后缀配对：

```text
docs/
├── quickstart.md       # English
├── quickstart.zh.md    # Chinese
├── assets/
└── images/
```

在 `mkdocs.yml` 的 `nav` 中添加英文文件路径，并在 `nav_translations` 中添加中文标签。两种语言的链接都使用英文源文件名，例如 `[规则](SAFETY_RULES.md)`，本地化插件会解析到对应语言页面。

命令、路径、配置键、谓词和 GUI 控件保持英文，说明文字进行翻译。使用明确标题、简短步骤和具体例子。程序源码和 GUI 继续保持英文。

统一采用指南格式：标题与简短介绍、显式页内目录、编号章节（`1.`、`2.`）、编号小节（`1.1`、`1.2`）、命令示例、参数表和引用块说明。Markdown 应同时适合在仓库和文档站中阅读。新页面需加入文档总目录，修改标题时保留已有锚点 ID。

<a id="_6"></a>

## 5. 避免参考内容过期

`docs/hooks.py` 在构建时直接从仓库配置文件生成下载内容，并从 `gui_modules/safety/catalog.py` 生成谓词表格，不导入仿真器。中文谓词解释位于 `docs/assets/predicates.zh.json`，缺少翻译时构建会报错。

主题、图标、字体设置和搜索资源均使用本地资源。搜索无需外部托管服务，页面也不依赖外部字体服务。

<a id="_7"></a>

## 6. 使用 GitHub Pages 发布

正式文档地址：[English](https://ethyn13.github.io/red-libero/) · [简体中文](https://ethyn13.github.io/red-libero/zh/)。

[Documentation 工作流](https://github.com/Ethyn13/red-libero/actions/workflows/docs.yml)会在拉取请求以及主分支相关文件更新时构建并检查文档。拉取请求只执行检查；主分支构建成功后自动部署到 GitHub Pages。也可以在主分支上选择 **Run workflow** 手动发布。

仓库采用 **Settings → Pages → Build and deployment → Source: GitHub Actions**。工作流只上传生成的文档站点，通过 github-pages 环境部署。部署令牌由 GitHub 提供，工作流无需保存个人访问令牌。

在本地复现线上构建：

```bash
export DOCS_SITE_URL=https://ethyn13.github.io/red-libero/
python -m mkdocs build --strict
python scripts/check_docs.py
```

工作流为构建和链接检查设置相同的站点地址，包含 /red-libero/ 路径前缀。未设置 DOCS_SITE_URL 时，本地预览继续使用默认的 localhost 地址。

如果使用 fork 仓库或其他托管地址，请修改工作流中的 DOCS_SITE_URL，并在对应仓库启用 GitHub Pages。[redvla.github.io](https://redvla.github.io)继续作为 RedVLA 项目主页。
