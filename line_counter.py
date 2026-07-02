#!/usr/bin/env python3
"""
line_counter.py

Walks a directory tree, counts lines in all recognized source/code files,
and prints a clean table of the files with the most lines, along with
each file's % share of the total line count, ending with a grand total.

Usage:
    python line_counter.py [path] [--top N] [--ext .py,.js] [--exclude dir1,dir2]

Examples:
    python line_counter.py .
    python line_counter.py ./my_project --top 25
    python line_counter.py . --exclude node_modules,.git,dist,build
"""

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# Extensions covered: systems languages, scripting, web/full-stack, config,
# markup, styles, shell, data, mobile, etc.
# ---------------------------------------------------------------------------
CODE_EXTENSIONS = {
    # C-family / systems
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx",
    ".cs", ".rs", ".go", ".swift", ".m", ".mm", ".zig", ".d",

    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy", ".clj", ".cljs",

    # Scripting / general purpose
    ".py", ".pyw", ".pyi", ".rb", ".php", ".pl", ".pm", ".lua",
    ".r", ".jl", ".dart", ".ex", ".exs", ".erl", ".hrl", ".hs",
    ".ml", ".mli", ".fs", ".fsx", ".nim", ".v", ".sol",

    # Web / full-stack front-end
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".styl",

    # Full-stack back-end / templating
    ".sql", ".graphql", ".gql", ".ejs", ".hbs", ".pug", ".twig",
    ".erb", ".jsp", ".asp", ".aspx",

    # Shell / scripting glue
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",

    # Config / data / markup often treated as "code"
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml",
    ".proto", ".dockerfile",

    # Docs-as-code (optional but commonly counted)
    ".md", ".rst",
}

# Filenames without extensions worth counting
SPECIAL_FILENAMES = {
    "Dockerfile", "Makefile", "CMakeLists.txt", "Rakefile",
    "Gemfile", "Procfile", 
}

DEFAULT_EXCLUDES = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv",
    "venv", "env", "dist", "build", ".next", ".nuxt", "target",
    ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
    "vendor", ".terraform", ".claude", ".cursor", ".cursor",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".DS_Store",
}


def count_lines(filepath):
    """Count lines in a file, tolerant of encoding issues."""
    try:
        with open(filepath, "rb") as f:
            data = f.read()
        # Fast line count on bytes; treat as text regardless of encoding
        if not data:
            return 0
        return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
    except (OSError, IOError):
        return None


def is_code_file(filename, allowed_ext):
    if filename in SPECIAL_FILENAMES:
        return True
    _, ext = os.path.splitext(filename)
    return ext.lower() in allowed_ext


def collect_files(root, allowed_ext, exclude_dirs):
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not d.startswith(".git")]
        for fname in filenames:
            if is_code_file(fname, allowed_ext):
                full = os.path.join(dirpath, fname)
                lines = count_lines(full)
                if lines is not None:
                    rel = os.path.relpath(full, root)
                    results.append((rel, lines))
    return results


def format_table(rows, total, top_n):
    """rows: list of (filepath, lines), sorted descending by lines."""
    display_rows = rows[:top_n]

    if not display_rows:
        print("No matching code files found.")
        return

    rank_w = max(4, len(str(len(display_rows))))
    path_w = max(9, min(70, max(len(r[0]) for r in display_rows)))
    lines_w = max(5, len(f"{max(r[1] for r in display_rows):,}"))
    pct_w = 7

    def fmt_row(rank, path, lines, pct):
        path_disp = path if len(path) <= path_w else "…" + path[-(path_w - 1):]
        return (f"{rank:<{rank_w}} | {path_disp:<{path_w}} | "
                f"{lines:>{lines_w},} | {pct:>{pct_w}.2f}%")

    header = fmt_row("Rank", "File", 0, 0.0)
    # Build header manually to avoid weird number formatting
    header = (f"{'Rank':<{rank_w}} | {'File':<{path_w}} | "
              f"{'Lines':>{lines_w}} | {'Share':>{pct_w}}")
    sep = "-" * len(header)

    print(sep)
    print(header)
    print(sep)

    for i, (path, lines) in enumerate(display_rows, start=1):
        pct = (lines / total * 100) if total else 0.0
        print(fmt_row(i, path, lines, pct))

    print(sep)
    shown_total = sum(l for _, l in display_rows)
    shown_pct = (shown_total / total * 100) if total else 0.0
    print(f"{'':<{rank_w}} | {'Shown subtotal':<{path_w}} | "
          f"{shown_total:>{lines_w},} | {shown_pct:>{pct_w}.2f}%")
    print(sep)
    print(f"{'':<{rank_w}} | {'TOTAL (all files)':<{path_w}} | "
          f"{total:>{lines_w},} | {100.00:>{pct_w}.2f}%")
    print(sep)


def main():
    parser = argparse.ArgumentParser(
        description="Count lines per code file and show top offenders in a table."
    )
    parser.add_argument("path", nargs="?", default=".", help="Root directory to scan (default: current dir)")
    parser.add_argument("--top", type=int, default=20, help="Number of top files to display (default: 20)")
    parser.add_argument("--ext", type=str, default="", help="Comma-separated list of extra extensions to include, e.g. .foo,.bar")
    parser.add_argument("--exclude", type=str, default="", help="Comma-separated list of extra directory names to exclude")
    args = parser.parse_args()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    allowed_ext = set(CODE_EXTENSIONS)
    if args.ext:
        for e in args.ext.split(","):
            e = e.strip()
            if e:
                if not e.startswith("."):
                    e = "." + e
                allowed_ext.add(e.lower())

    exclude_dirs = set(DEFAULT_EXCLUDES)
    if args.exclude:
        exclude_dirs.update(d.strip() for d in args.exclude.split(",") if d.strip())

    files = collect_files(root, allowed_ext, exclude_dirs)
    files.sort(key=lambda x: x[1], reverse=True)
    total = sum(l for _, l in files)

    print(f"\nScanned: {root}")
    print(f"Files matched: {len(files)}\n")

    format_table(files, total, args.top)


if __name__ == "__main__":
    main()
