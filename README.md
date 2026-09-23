# EaToMd

Pipe-and-filter pipeline that exports a Sparx Enterprise Architect repository
to a Markdown "site", mirroring EA's native HTML export: one page per
package, nested recursively, with diagrams rendered to images and elements
cross-linked the way EA's own export does.

## Pipeline

```
EA repository
    -> eatomd.ea_source.extract_model        (EA COM -> IR)
    -> eatomd.diagram_exporter.export_diagrams (renders each Diagram to PNG via EA)
    -> eatomd.markdown_renderer.render_model  (IR -> {path: markdown})
    -> eatomd.git_sink.write_files / commit / push  (write to disk, git commit, git push)
```

Each stage is a plain function taking the previous stage's output; see
`src/eatomd/pipeline.py` for how they're wired together. Only `ea_source.py`
and `diagram_exporter.py` touch the EA COM API - everything from
`markdown_renderer.py` onward operates on the plain dataclasses in
`model.py` and is unit-tested without EA installed (see `tests/`).

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
`origin`) once it's done.

## CI/CD watch mode

To keep the Markdown export continuously in sync with the EA repository,
run in watch mode instead of one-shot: it re-exports every N minutes and
pushes any change straight to the remote.

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

## Notes / next steps to validate on a real repository

- `ea_source.py` uses the documented EA Automation API
  (`Repository.Models`, `Package.Packages/Elements/Diagrams`,
  `Element.Connectors/TaggedValues`, `Project.PutDiagramImageToFile`).
  This hasn't been exercised against a live EA 15.2 instance in this
  environment (no EA install here) - run it against your repository and
  check connector direction/type formatting and diagram image quality.
- Only `Connector` relationships are exported as cross-references today;
  extend `_extract_element` in `ea_source.py` if you also want e.g.
  generalizations shown separately, diagram-only elements without a
  connector, or package-level diagrams (data flow / requirements matrices). 
