"""The agent skill shipped with ptestgen (``ptestgen/skill``): install it or print it."""
from __future__ import annotations

import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent / "skill"
MARKER = ".ptestgen-skill"
DEFAULT_TARGET = Path.home() / ".claude" / "skills" / "ptestgen"


def skill_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("ptestgen")
    except PackageNotFoundError:
        return "unknown"


def install(target: Path = DEFAULT_TARGET, force: bool = False) -> Path:
    """Copy the skill to ``target``. A folder installed by ptestgen (it has the marker file)
    is replaced; any other existing folder needs ``force``."""
    target = Path(target).expanduser()
    if target.exists():
        if not (target / MARKER).exists() and not force:
            raise FileExistsError(f"{target} exists and was not installed by ptestgen; pass --force to replace it.")
        shutil.rmtree(target)
    shutil.copytree(SKILL_DIR, target, ignore=shutil.ignore_patterns("__pycache__"))
    (target / MARKER).write_text(f"ptestgen {skill_version()}\n", encoding="utf-8")
    return target


def agents_text() -> str:
    """What ``ptestgen --agents`` prints: the skill itself, with the folder of its references."""
    body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    return f"{body}\n\n---\nReferences: {SKILL_DIR / 'references'} (ptestgen {skill_version()}). Install the skill with `ptestgen skill install`.\n"


def handle_skill(args) -> None:
    if args.skill_command == "install":
        path = install(Path(args.dir) if args.dir else DEFAULT_TARGET, force=args.force)
        print(f"Skill installed in {path}")
    else:
        print(SKILL_DIR)


def add_parser(subparsers, parents) -> None:
    parser = subparsers.add_parser("skill", parents=parents, help="Install the agent skill (or print where it is).")
    sub = parser.add_subparsers(dest="skill_command", required=True)
    p = sub.add_parser("install", help=f"Copy the skill to an agent's skills folder (default: {DEFAULT_TARGET}).")
    p.add_argument("--dir", help="Target folder, e.g. .claude/skills/ptestgen inside a project.")
    p.add_argument("--force", action="store_true", help="Replace a folder that was not installed by ptestgen.")
    sub.add_parser("path", help="Print the folder of the skill inside the installed package.")
    parser.set_defaults(func=handle_skill)
