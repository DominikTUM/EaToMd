"""Orchestrator: wires the pipe-and-filter stages together.

    EA repository --> ea_source.extract_model --> diagram_exporter.export_diagrams
                   --> <format>_renderer.render_model --> git_sink.write_files/commit/push

Each arrow is a plain function call passing the IR (model.Model) or a
{path: content} dict along; there is no shared mutable pipeline object, so
each stage can be tested and reasoned about independently. The render step
is selected by --output-format: every format is an ExportVisitor subclass
(see export_visitor.py) sharing the same tree-walk and package layout, so
adding a new one is a new visitor, not a change to this orchestrator.

Two entry points:
  - run():   a single one-shot export (optionally commit + push).
  - watch(): CI/CD-style loop that re-runs run() every N minutes. Since
    git_sink.commit() only commits when the rendered output actually
    changed, an idle poll (no model changes) is a fast no-op: no empty
    commits, no unnecessary pushes.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from typing import Optional

from . import diagram_exporter, ea_source, git_sink, latex_renderer, markdown_renderer

RENDERERS = {
    "markdown": markdown_renderer,
    "latex": latex_renderer,
}

DIAGRAM_FORMATS = ("png", "svg", "emf", "bmp", "jpg")


def run(
    ea_project_path: str,
    output_dir: str,
    root_package_name: Optional[str] = None,
    commit_message: str = "Update model export",
    do_commit: bool = True,
    do_push: bool = False,
    remote: str = "origin",
    output_format: str = "markdown",
    diagram_format: str = "png",
) -> bool:
    """Run one export. Returns True if a new commit was created."""
    renderer = RENDERERS[output_format]

    repo = ea_source.open_repository(ea_project_path)
    try:
        model = ea_source.extract_model(repo, root_package_name=root_package_name)
        diagram_exporter.export_diagrams(repo, model, output_dir, image_format=diagram_format)
    finally:
        ea_source.close_repository(repo)

    files = renderer.render_model(model)
    git_sink.write_files(output_dir, files)

    if not do_commit:
        return False

    committed = git_sink.commit(output_dir, commit_message)
    if committed and do_push:
        git_sink.push(output_dir, remote=remote)
    return committed


def watch(
    ea_project_path: str,
    output_dir: str,
    interval_minutes: float,
    root_package_name: Optional[str] = None,
    remote: str = "origin",
    output_format: str = "markdown",
    diagram_format: str = "png",
) -> None:
    """CI/CD mode: poll the EA repository every interval_minutes, and for
    any run that produces a real change, commit and push it to `remote`.
    Runs until interrupted (Ctrl+C). Errors in one iteration are logged and
    do not stop the loop, so a transient EA/network failure doesn't require
    restarting the watcher.
    """
    print(f"[eatomd] watching '{ea_project_path}' every {interval_minutes} min, pushing to '{remote}'")
    while True:
        started_at = time.monotonic()
        timestamp = datetime.now().isoformat(timespec="seconds")
        try:
            committed = run(
                ea_project_path=ea_project_path,
                output_dir=output_dir,
                root_package_name=root_package_name,
                commit_message=f"Automated model export {timestamp}",
                do_commit=True,
                do_push=True,
                remote=remote,
                output_format=output_format,
                diagram_format=diagram_format,
            )
            status = "pushed update" if committed else "no changes"
            print(f"[eatomd] {timestamp}: {status}")
        except Exception as exc:  # keep the watch loop alive across transient failures
            print(f"[eatomd] {timestamp}: export failed: {exc}", file=sys.stderr)

        elapsed = time.monotonic() - started_at
        sleep_for = max(0.0, interval_minutes * 60 - elapsed)
        time.sleep(sleep_for)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export a Sparx EA repository to Markdown or LaTeX.")
    parser.add_argument("ea_project_path", help="Path to the .qea/.eapx project, or an EA connection string")
    parser.add_argument("output_dir", help="Folder (git repo) to write the Markdown export into")
    parser.add_argument("--root-package", default=None, help="Only export this top-level package")
    parser.add_argument("--message", default="Update model export", help="Git commit message (one-shot mode)")
    parser.add_argument("--no-commit", action="store_true", help="Write files but skip the git commit")
    parser.add_argument("--push", action="store_true", help="Push after committing (one-shot mode)")
    parser.add_argument("--remote", default="origin", help="Git remote to push to (default: origin)")
    parser.add_argument(
        "--output-format",
        choices=sorted(RENDERERS),
        default="markdown",
        help="Export format (default: markdown)",
    )
    parser.add_argument(
        "--diagram-format",
        choices=DIAGRAM_FORMATS,
        default="png",
        help="Diagram image format (default: png). 'svg' tries EA's native SVG export "
        "(EA 16.1+ or the SVG add-in) and falls back to EMF->SVG conversion via Inkscape "
        "if that's unavailable (e.g. on EA 15.2) - see README.",
    )
    parser.add_argument(
        "--watch-minutes",
        type=float,
        default=None,
        help="CI/CD mode: re-check the EA repository every N minutes and push any changes to --remote, "
        "instead of exporting once and exiting",
    )
    args = parser.parse_args(argv)

    if args.watch_minutes is not None:
        watch(
            ea_project_path=args.ea_project_path,
            output_dir=args.output_dir,
            interval_minutes=args.watch_minutes,
            root_package_name=args.root_package,
            remote=args.remote,
            output_format=args.output_format,
            diagram_format=args.diagram_format,
        )
        return 0

    run(
        ea_project_path=args.ea_project_path,
        output_dir=args.output_dir,
        root_package_name=args.root_package,
        commit_message=args.message,
        do_commit=not args.no_commit,
        do_push=args.push,
        remote=args.remote,
        output_format=args.output_format,
        diagram_format=args.diagram_format,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
