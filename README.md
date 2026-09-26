# EaToMd

Pipe-and-filter pipeline that exports a Sparx Enterprise Architect repository
to Markdown or LaTeX, mirroring EA's native HTML export: one page per
package, nested recursively, with diagrams rendered to images and elements
cross-linked the way EA's own export does.

## Pipeline

```
EA repository
    -> eatomd.ea_source.extract_model          (EA COM -> IR)
    -> eatomd.diagram_exporter.export_diagrams  (renders each Diagram to an image via EA)
    -> <format>_renderer.render_model           (IR -> {path: rendered text})
    -> eatomd.git_sink.write_files / commit / push  (write to disk, git commit, git push)
```

Each stage is a plain function taking the previous stage's output; see
`src/eatomd/pipeline.py` for how they're wired together. Only `ea_source.py`
and `diagram_exporter.py` touch the EA COM API - everything from the render
step onward operates on the plain dataclasses in `model.py` and is
unit-tested without EA installed (see `tests/`).

The render step is a Visitor: `markdown_renderer.MarkdownVisitor` and
`latex_renderer.LatexVisitor` both subclass `export_visitor.ExportVisitor`,
sharing the same tree walk and on-disk package folder layout
(`layout.assign_package_dirs`) while each format decides for itself how to
turn a package/diagram/element into text and how to cross-link them (see
`--output-format` below). Adding a third format means writing one more
`ExportVisitor` subclass, not touching the orchestrator or the other
formats.

## Requirements

- Windows, with Sparx Enterprise Architect 15.2 installed and licensed
  (the exporter drives EA itself via COM Automation to read the model and
  render diagrams with full fidelity).
- Python 3.9+
- `pip install -r requirements.txt` (installs `pywin32` on Windows)

## Usage

```
python -m eatomd.pipeline "C:\path\to\project.qea" "C:\path\to\output-repo" \
    --root-package "My System" \
    --message "Export model"
```

Run with `--root-package` omitted to export every top-level package in the
model. Pass `--no-commit` to write files without creating a git commit.
Add `--push` to push a one-shot export's commit to `--remote` (default
`origin`) once it's done. Add `--output-format latex` to export LaTeX
(`.tex`) instead of Markdown - default is `markdown`.

LaTeX output is one `.tex` file per package (same folder layout as
Markdown), `\input` together into a single document starting from the
root package's `index.tex` (which carries the `\documentclass`/
`\begin{document}` preamble). Compile it with your usual LaTeX toolchain,
e.g. `pdflatex index.tex` from the output directory (requires the
`graphicx` and `hyperref` packages, both loaded automatically in the
preamble). Unlike Markdown's per-file relative links, cross-references use
`\label`/`\hyperref` keyed on each element/diagram's GUID, since `\input`
makes the whole tree one document where labels must be unique globally.

## Diagram image format

By default diagrams are exported as PNG. Use `--diagram-format` to pick
`png` (default), `svg`, `emf`, `bmp` or `jpg`.

`svg` needs care: Sparx only added native SVG diagram export to EA in
**16.1** (older versions need a separate community "SVG Diagram Export
Add-In"). On EA 15.2 without that add-in, `diagram_exporter.py` first
tries the native SVG export and, if EA rejects it, automatically falls
back to exporting the always-supported vector format EMF and converting
that to SVG with [Inkscape](https://inkscape.org) (must be on `PATH`) - so
either way you get a real vector SVG, not a rasterized one. If neither
path works (e.g. Inkscape isn't installed), the export fails with a clear
error telling you to install Inkscape rather than silently producing a
bad or missing image.

For the LaTeX output format specifically, SVG diagrams are embedded with
`\includesvg` (from the `svg` package, already added to the generated
preamble) instead of `\includegraphics`, since plain `\includegraphics`
can't read SVG directly. Compiling then needs Inkscape on `PATH` and
`pdflatex -shell-escape` (the `svg` package shells out to Inkscape at
compile time to rasterize each figure) - if you'd rather not deal with
`-shell-escape`, use `--diagram-format png` for the LaTeX output instead.

## CI/CD watch mode

To keep the export continuously in sync with the EA repository, run in
watch mode instead of one-shot: it re-exports every N minutes and pushes
any change straight to the remote. `--output-format` applies here too.

```
python -m eatomd.pipeline "C:\path\to\project.qea" "C:\path\to\output-repo" \
    --watch-minutes 15 \
    --remote origin
```

Each tick re-runs the full pipeline and calls `git commit`; because that
commit is skipped whenever the rendered output is byte-identical to what's
already committed (see `git_sink.commit`), an idle poll with no model
changes does not create empty commits or trigger a push - it just logs
`no changes` and waits for the next tick. A failed tick (e.g. EA or the
network is temporarily unavailable) is logged to stderr and does not stop
the loop; the next tick retries. `output_dir` must already have a
`origin` remote configured (`git remote add origin <url>`) before you
start the watcher, since `git push` needs somewhere to push to.

Run it as a permanent background process with your usual tooling (a
Windows Scheduled Task calling this command at logon, `pythonw` for a
console-less run, or a Windows Service wrapper such as NSSM) - the
process itself just loops and sleeps, it doesn't daemonize on its own.

## Releasing

Pushing a tag matching `v*.*.*` (e.g. `v0.1.0`) triggers the CD workflow
(`.github/workflows/cd.yml`): it runs the tests, builds the sdist/wheel
with `python -m build`, and publishes them as downloadable artifacts on a
new GitHub Release for that tag.

```
git tag v0.1.0
git push origin v0.1.0
```

## Notes / next steps to validate on a real repository

- `ea_source.py` uses the documented EA Automation API
  (`Repository.Models`, `Package.Packages/Elements/Diagrams`,
  `Element.Connectors/TaggedValues`, `Project.PutDiagramImageToFile`).
  This hasn't been exercised against a live EA 15.2 instance in this
  environment (no EA install here) - run it against your repository and
  check connector direction/type formatting and diagram image quality.
  In particular, the SVG native-export-then-EMF-fallback logic in
  `diagram_exporter.py` is written from public documentation/forum
  examples of `PutDiagramImageToFile`, not verified against a real EA
  15.2 install - confirm it picks the fallback path (or the native path,
  if you do have the SVG add-in) as expected on your setup.
- Only `Connector` relationships are exported as cross-references today;
  extend `_extract_element` in `ea_source.py` if you also want e.g.
  generalizations shown separately, diagram-only elements without a
  connector, or package-level diagrams (data flow / requirements matrices). 
