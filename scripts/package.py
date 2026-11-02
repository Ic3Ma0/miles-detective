#!/usr/bin/env python3
"""Build a versioned skill package and update the delivery index.

Usage:
    python3 scripts/package.py --version r10
    python3 scripts/package.py --version r11 --install

The zip always contains a top-level `miles-detective/` directory. Case
directories (`examples/`), repo-level agent config (`docs/`, `CLAUDE.md`),
and maintainer tooling are excluded: the package is the skill, not the
research workspace.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

PACKAGE_NAME = "miles-detective"
EXCLUDE_DIRS = {".git", "examples", "evals", "docs", "__pycache__"}
EXCLUDE_FILES = {".DS_Store", ".gitignore", "CLAUDE.md", "GLOSSARY.md"}
EXCLUDE_RELATIVE = {"scripts/package.py", "scripts/test_package.py"}
INDEX_NAME = "交付包索引.json"
PACKAGE_RE = re.compile(r"^Miles-侦探-Skill-r(\d+)\.zip$")


def repo_root():
    return Path(__file__).resolve().parent.parent


def is_excluded(relative):
    parts = relative.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    if relative.name in EXCLUDE_FILES:
        return True
    if relative.as_posix() in EXCLUDE_RELATIVE:
        return True
    return relative.suffix == ".pyc"


def collect_files(root):
    root = Path(root)
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not is_excluded(relative):
            files.append(relative)
    return files


def build_zip(root, files, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            archive.write(Path(root) / relative, f"{PACKAGE_NAME}/{relative.as_posix()}")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return len(files), output_path.stat().st_size, digest


def load_index(path):
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def current_package(index):
    candidates = []
    for name, meta in index.items():
        match = PACKAGE_RE.match(name)
        if match and not meta.get("superseded_by"):
            candidates.append((int(match.group(1)), name))
    return max(candidates)[1] if candidates else None


def update_index(path, zip_name, files, size, digest, installed_to=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = load_index(path)
    previous = current_package(index)
    entry = {"files": files, "bytes": size, "sha256": digest}
    if previous:
        entry["supersedes"] = previous
        index[previous]["superseded_by"] = zip_name
    if installed_to:
        entry["installed_to"] = installed_to
    index[zip_name] = entry
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry, previous


def sync_install(root, files, target):
    root = Path(root)
    target = Path(target).expanduser()
    staging = Path(tempfile.mkdtemp(prefix="miles-detective-package-"))
    try:
        for relative in files:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
        backup = None
        if target.exists():
            backup = target.with_name(target.name + ".backup")
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
        shutil.copytree(staging, target)
        if backup is not None:
            shutil.rmtree(backup)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True, help="版本标识，如 r10")
    parser.add_argument("--output-dir", default=None, help="压缩包输出目录，默认 ../outputs")
    parser.add_argument("--install", action="store_true", help="同步到 ~/.claude/skills/miles-detective")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的同名压缩包")
    args = parser.parse_args()

    root = repo_root()
    output_dir = Path(args.output_dir) if args.output_dir else root.parent / "outputs"
    zip_name = f"Miles-侦探-Skill-{args.version}.zip"
    output_path = output_dir / zip_name
    if output_path.exists() and not args.force:
        parser.exit(1, f"已存在 {output_path}；如需覆盖请加 --force\n")

    files = collect_files(root)
    if not files:
        parser.exit(1, "没有可打包文件\n")
    count, size, digest = build_zip(root, files, output_path)
    installed_to = None
    if args.install:
        target = sync_install(root, files, Path.home() / ".claude" / "skills" / PACKAGE_NAME)
        installed_to = str(target).replace(str(Path.home()), "~")

    update_index(output_dir / INDEX_NAME, zip_name, count, size, digest, installed_to)
    print(f"已打包 {zip_name}：{count} 个文件，{size} 字节")
    print(f"SHA-256 {digest}")
    if installed_to:
        print(f"已同步安装到 {installed_to}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"打包错误：{exc}\n")
