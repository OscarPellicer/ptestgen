"""Course record (``ai4exams.yaml``): how the AI4Exams tools were used in one course.

One YAML file per course holds the launch configuration of every step (exam export,
scan correction, grading, mark combination), the paths to its artifacts, the decisions
taken (voided questions, policies) and two blocks computed from the artifacts:
``metrics`` (LLM calls, tokens, cost, marks) and ``edits`` (where the teacher changed
the model's grade). An agent reads it to repeat or extend the work in a later year.

Paths in a step are relative to the step's ``cwd`` (default: the folder of the YAML).
"""
from __future__ import annotations

import csv
import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterator, Optional

SCHEMA = "ai4exams-course/1"
FILE_NAME = "ai4exams.yaml"

# USD per million tokens: input, output, cache read. List prices; override with `prices:` in the YAML.
DEFAULT_PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}

# Arguments that name existing inputs; `validate` checks that they exist.
INPUT_ARGS = {"input_path", "exam_dir", "index_csv", "rubric", "example", "roster", "custom_header",
              "input_csv", "lab_feedback", "exam_scores", "mc_correction_dir", "results"}

# `pevaluate <folder>` resolves these relative to <folder>, not to the working directory.
LAB_FOLDER_ARGS = {"rubric", "example"}

KEY_PATTERN = re.compile(r"\b(sk-ant-[\w-]{10,}|sk-or-[\w-]{10,}|sk-[A-Za-z0-9]{20,}|AIza[\w-]{20,}|gsk_[\w]{20,}|r8_[\w]{20,})")


# --- Loading and saving --------------------------------------------------------------------

def _yaml():
    from ruamel.yaml import YAML
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def find_course_file(path: Optional[str] = None) -> Path:
    """The course YAML: ``path`` itself, ``path/ai4exams.yaml``, or the first one found
    in the current folder or its parents."""
    if path:
        p = Path(path)
        if p.is_dir():
            p = p / FILE_NAME
        if not p.exists():
            raise FileNotFoundError(f"Course file not found: {p}")
        return p.resolve()
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        if (folder / FILE_NAME).exists():
            return folder / FILE_NAME
    raise FileNotFoundError(f"No {FILE_NAME} in {here} or its parents. Create one with `ptestgen course init`.")


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return _yaml().load(f) or {}


def save(path: Path, data) -> None:
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        _yaml().dump(data, f)
    os.replace(tmp, path)


# --- Steps -------------------------------------------------------------------------------

def iter_steps(data) -> Iterator[tuple[str, str, dict]]:
    for assessment_id, assessment in (data.get("assessments") or {}).items():
        for step_id, step in ((assessment or {}).get("steps") or {}).items():
            yield str(assessment_id), str(step_id), step


def get_step(data, ref: str) -> tuple[str, str, dict]:
    """``"P2.correct"`` -> (assessment id, step id, step)."""
    if "." not in ref:
        raise ValueError(f"Name a step as ASSESSMENT.STEP (e.g. P1.correct), not '{ref}'.")
    assessment_id, step_id = ref.split(".", 1)
    for a, s, step in iter_steps(data):
        if a == assessment_id and s == step_id:
            return a, s, step
    raise KeyError(f"Step '{ref}' not found. Steps: {', '.join(f'{a}.{s}' for a, s, _ in iter_steps(data))}")


def step_kind(step: dict) -> str:
    words = str(step.get("command", "")).split()
    if words[:2] == ["ptestgen", "export"]:
        return "export"
    if words[:3] == ["ptestgen", "correct", "pexams"] or words[:2] == ["pexams", "correct"]:
        return "correct_pexams"
    if words[:1] == ["pevaluate"]:
        sub = words[1] if len(words) > 1 else ""
        return {"exam-open": "exam_open", "exam-free": "exam_free", "combine-marks": "combine",
                "moodle-csv": "moodle_csv", "poliformat-zip": "poliformat_zip"}.get(sub, "lab")
    return "other"


def step_cwd(step: dict, base: Path) -> Path:
    return (base / str(step.get("cwd", "."))).resolve()


def render_args(step: dict) -> list[str]:
    """The step's command line: ``command``, ``positional`` and ``args`` ({flag: value}).
    ``True`` adds a bare flag, ``False``/``None`` omits it, a list gives several values."""
    argv = shlex.split(str(step["command"]))
    argv += [str(p) for p in step.get("positional") or []]
    for key, value in (step.get("args") or {}).items():
        flag = "--" + str(key).replace("_", "-")
        if value is None or value is False:
            continue
        if value is True:
            argv.append(flag)
        elif isinstance(value, (list, tuple)):
            argv += [flag, *[str(v) for v in value]]
        else:
            argv += [flag, str(value)]
    return argv


def step_output(step: dict, base: Path) -> Optional[Path]:
    """The folder (or file) the step writes: ``output``, else ``--output-dir``/``--output``;
    lab grading writes to ``<submissions folder>/feedback``."""
    cwd = step_cwd(step, base)
    args = step.get("args") or {}
    out = step.get("output") or args.get("output_dir") or args.get("output") or args.get("feedback_dir")
    if out:
        return (cwd / str(out)).resolve()
    if step_kind(step) == "lab" and step.get("positional"):
        return (cwd / str(step["positional"][0]) / "feedback").resolve()
    return None


def rerun_warnings(step: dict, base: Path) -> list[str]:
    """What a rerun would overwrite. Empty when the step has not run yet."""
    out = step_output(step, base)
    args = step.get("args") or {}
    kind = step_kind(step)
    warnings = []
    if step.get("locked"):
        warnings.append("locked: this step's result was printed or published (`locked: true`).")
    if out is None or not out.exists():
        return warnings
    if kind == "export":
        warnings.append(f"{out} exists: a new export replaces the PDFs and question order. If the exam was "
                        "printed, the scans no longer match the new PDFs.")
    elif kind == "correct_pexams" and not args.get("only_analysis"):
        warnings.append(f"{out} exists: correcting the scans again rewrites correction_results.csv "
                        "(manual fixes to it are lost). Use only_analysis to recompute marks (e.g. after voiding).")
    elif kind in ("exam_open", "exam_free", "lab") and args.get("force_regrade"):
        warnings.append(f"force_regrade regrades everything in {out}: teacher edits in the YAML files are lost.")
    elif kind == "lab":
        warnings.append(f"{out} exists: lab grading writes new feedback files for the submissions it grades.")
    elif kind in ("combine", "moodle_csv"):
        warnings.append(f"{out} exists and will be rewritten (cheap: no LLM calls).")
    elif kind == "poliformat_zip":
        warnings.append(f"{out} exists and will be rewritten (cheap: no LLM calls). If it was already uploaded, "
                        "a new upload replaces the grades and comments in PoliformaT.")
    return warnings


# --- Validation ----------------------------------------------------------------------------

def validate(data, base: Path) -> list[tuple[str, str]]:
    """(level, message) pairs; level is ``error``, ``warning`` or ``info``."""
    issues = []
    if data.get("schema") != SCHEMA:
        issues.append(("error", f"schema should be '{SCHEMA}', found {data.get('schema')!r}."))
    if not (data.get("course") or {}).get("name"):
        issues.append(("error", "course.name is missing."))
    env_file = (data.get("environment") or {}).get("env_file")
    if env_file and not (base / str(env_file)).exists():
        issues.append(("warning", f"environment.env_file not found: {env_file}"))
    text = Path(base / FILE_NAME).read_text(encoding="utf-8") if (base / FILE_NAME).exists() else ""
    if KEY_PATTERN.search(text):
        issues.append(("error", "The file seems to contain an API key. Keep keys in the .env file and name only the variable."))
    if not data.get("assessments"):
        issues.append(("warning", "No assessments yet."))
    for assessment_id, step_id, step in iter_steps(data):
        ref = f"{assessment_id}.{step_id}"
        if not isinstance(step, dict) or not step.get("command"):
            issues.append(("error", f"{ref}: every step needs a `command`."))
            continue
        if str(step["command"]).split()[0] not in ("ptestgen", "pexams", "pevaluate"):
            issues.append(("warning", f"{ref}: command does not start with ptestgen, pexams or pevaluate."))
        cwd = step_cwd(step, base)
        if not cwd.exists():
            issues.append(("error", f"{ref}: cwd not found: {cwd}"))
            continue
        paths = [("positional", p) for p in step.get("positional") or []]
        for key, value in (step.get("args") or {}).items():
            if key in INPUT_ARGS and value not in (None, True, False):
                paths += [(key, v) for v in (value if isinstance(value, (list, tuple)) else [value])]
        for key, value in paths:
            # Submission grading reads the rubric and the example from the submissions folder.
            folder = cwd / str(step["positional"][0]) if step_kind(step) == "lab" and key in LAB_FOLDER_ARGS else cwd
            if not (folder / str(value)).exists():
                issues.append(("warning", f"{ref}: {key} not found: {value}"))
        out = step_output(step, base)
        if out is None:
            issues.append(("info", f"{ref}: no output path (set `output:`)."))
        elif not out.exists():
            issues.append(("info", f"{ref}: not run yet ({out.name} does not exist)."))
    return issues


# --- Metrics ---------------------------------------------------------------------------------

def _read_csv(path: Path, **kwargs) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        return list(csv.DictReader(f, delimiter=delimiter, **kwargs))


def _float(value) -> Optional[float]:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _summary(values: list[float]) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    values = sorted(values)
    return {"n": len(values), "mean": round(mean(values), 3), "median": round(values[len(values) // 2], 3),
            "min": round(values[0], 3), "max": round(values[-1], 3)}


def llm_call_metrics(log_path: Path, prices: dict) -> dict:
    calls = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    calls.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    tokens_in = tokens_out = tokens_cache = 0
    cost, priced = 0.0, True
    for call in calls:
        usage = call.get("usage") or {}
        i, o, c = (int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens"))
        tokens_in, tokens_out, tokens_cache = tokens_in + i, tokens_out + o, tokens_cache + c
        price = prices.get(call.get("model_served") or call.get("model_requested"))
        if price is None:
            priced = False
            continue
        price = tuple(price) + (price[0] * 0.1,) * (3 - len(price))
        cost += (i * price[0] + o * price[1] + c * price[2]) / 1e6
    latencies = [c.get("latency_s") for c in calls if isinstance(c.get("latency_s"), (int, float))]
    return {
        "calls": len(calls),
        "models": dict(Counter(c.get("model_served") or c.get("model_requested") for c in calls)),
        "effort": dict(Counter(str(c.get("effort")) for c in calls)),
        "purposes": dict(Counter(c.get("purpose") for c in calls)),
        "fallbacks": sum(bool(c.get("fallback_used")) for c in calls),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cache_read_tokens": tokens_cache,
        "cost_usd": round(cost, 3) if priced else None,
        "latency_s": {"total": round(sum(latencies), 1), "mean": round(mean(latencies), 2)} if latencies else None,
        "first_call_utc": min((c.get("timestamp_utc") for c in calls if c.get("timestamp_utc")), default=None),
    }


def _manifest_metrics(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    llm = manifest.get("llm") or {}
    packages = {name: f"{info.get('version')}" + (f" ({info['git_commit']})" if info.get("git_commit") else "")
                for name, info in (manifest.get("packages") or {}).items()
                if name in ("ptestgen", "pexams", "pevaluate")}
    return {"started_utc": manifest.get("started_utc"), "model": llm.get("model"), "effort": llm.get("effort"),
            "packages": packages}


def _result_metrics(kind: str, out: Path) -> dict:
    if kind == "export" and out.is_dir():
        pdfs = sorted(p for p in out.glob("exam_model_*.pdf") if re.fullmatch(r"exam_model_\w+\.pdf", p.name))
        result = {"models": len(pdfs)}
        try:
            import pymupdf
            result["pages_per_model"] = sorted({len(pymupdf.open(p)) for p in pdfs})
        except Exception:
            pass
        areas = out / "open_answer_areas.json"
        if areas.exists():
            result["open_answer_boxes"] = len(json.loads(areas.read_text(encoding="utf-8")))
        questions = sorted(out.glob("exam_model_*_questions.json"))
        if questions:
            qs = json.loads(questions[0].read_text(encoding="utf-8")).get("questions", [])
            result["questions"] = len(qs)
            result["open_questions"] = sum(q.get("question_type") == "open_answer" for q in qs)
        return result
    if kind == "correct_pexams" and (out / "correction_results.csv").exists():
        rows = _read_csv(out / "correction_results.csv")
        result = {"exams": len(rows)}
        read = [r for r in rows if r.get("ocr_student_id") is not None]
        if read:
            norm = lambda v: re.sub(r"[^0-9A-Z]", "", str(v or "").upper())
            result["id_read_differs_from_final"] = sum(norm(r["ocr_student_id"]) != norm(r.get("student_id")) for r in read)
        if (out / "final_marks.csv").exists():
            marks = [r for r in _read_csv(out / "final_marks.csv") if (_float(r.get("max_score")) or 0) > 0]
            if marks:  # an exam with only open answers has no multiple-choice mark
                result["mark"] = _summary([_float(r.get("mark")) for r in marks])
        return result
    if kind in ("exam_open", "exam_free") and (out / "open_scores.csv").exists():
        rows = _read_csv(out / "open_scores.csv")
        ratios, per_student = [], {}
        for r in rows:
            score, top = _float(r.get("score")), _float(r.get("max_score"))
            if score is not None and top:
                ratios.append(score / top)
                s = per_student.setdefault(r.get("student_id"), [0.0, 0.0])
                s[0], s[1] = s[0] + score, s[1] + top
        result = {"students": len({r.get("student_id") for r in rows}), "responses": len(rows),
                  "not_graded": sum(r.get("status") in ("error", "pending", "missing_crop", "missing_question") for r in rows),
                  "score_ratio": _summary(ratios),
                  "mark": _summary([10 * s / m for s, m in per_student.values() if m])}
        if (out / "overall_marks.csv").exists():
            result["overall_mark"] = _summary([_float(r.get("mark")) for r in _read_csv(out / "overall_marks.csv")])
        return result
    if kind == "lab" and out.is_dir():
        import yaml
        marks = []
        for path in sorted(out.glob("*.yaml")):
            item = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            marks.append(_float(item.get("mark")))
        return {"submissions": len(marks), "mark": _summary(marks)}
    if kind == "combine" and out.is_file():
        rows = _read_csv(out)
        return {"students": len(rows), "final_mark": _summary([_float(r.get("final_mark")) for r in rows]),
                "without_lab": sum(not r.get("lab_mark") for r in rows),
                "without_exam": sum(not r.get("exam_mark") for r in rows),
                "lab_conflicts": sum(bool(r.get("lab_conflict")) for r in rows)}
    return {}


def step_metrics(step: dict, base: Path, prices: Optional[dict] = None) -> Optional[dict]:
    """Metrics of a step computed from its artifacts, or None if it has not run."""
    out = step_output(step, base)
    if out is None or not out.exists():
        return None
    prices = {**DEFAULT_PRICES, **{k: tuple(v) for k, v in (prices or {}).items()}}
    folder = out if out.is_dir() else out.parent
    metrics = {}
    if (folder / "run_manifest.json").exists():
        metrics["run"] = _manifest_metrics(folder / "run_manifest.json")
    if (folder / "llm_calls.jsonl").exists():
        metrics["llm"] = llm_call_metrics(folder / "llm_calls.jsonl", prices)
    metrics.update(_result_metrics(step_kind(step), out))
    metrics["computed_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return metrics


# --- Teacher edits ---------------------------------------------------------------------------

def step_edits(step: dict, base: Path) -> Optional[dict]:
    """Where the final grade differs from the model's (kept in each ``grader`` block), and,
    for scan correction, where the ID read from the header differs from the final one."""
    out = step_output(step, base)
    if out is None or not out.exists():
        return None
    kind = step_kind(step)
    import yaml
    items, compared, without_original, diffs = [], 0, 0, []
    if kind in ("exam_open", "exam_free") and (out / "open_evaluations.yaml").exists():
        data = yaml.safe_load((out / "open_evaluations.yaml").read_text(encoding="utf-8")) or {}
        for r in data.get("responses", []):
            grader = r.get("grader") or {}
            if "score" not in grader:
                without_original += 1
                continue
            compared += 1
            llm, final = _float(grader.get("score")), _float(r.get("score"))
            feedback_changed = str(grader.get("feedback") or "").strip() != str(r.get("feedback") or "").strip()
            if llm != final or feedback_changed:
                item = {"student_id": str(r.get("student_id")), "question": str(r.get("original_id") or r.get("question_id")),
                        "llm_score": llm, "score": final}
                if feedback_changed:
                    item["feedback"] = r.get("feedback")
                items.append(item)
                if llm is not None and final is not None:
                    diffs.append(abs(final - llm))
    elif kind == "lab" and out.is_dir():
        for path in sorted(out.glob("*.yaml")):
            r = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            grader = r.get("grader") or {}
            if "mark" not in grader:
                without_original += 1
                continue
            compared += 1
            llm, final = _float(grader.get("mark")), _float(r.get("mark"))
            feedback_changed = str(grader.get("feedback") or "").strip() != str(r.get("feedback") or "").strip()
            if llm != final or feedback_changed:
                item = {"submission": str(r.get("source_id") or path.stem), "llm_mark": llm, "mark": final}
                if feedback_changed:
                    item["feedback_changed"] = True
                items.append(item)
                if llm is not None and final is not None:
                    diffs.append(abs(final - llm))
    elif kind == "correct_pexams" and (out / "correction_results.csv").exists():
        norm = lambda v: re.sub(r"[^0-9A-Z]", "", str(v or "").upper())
        for r in _read_csv(out / "correction_results.csv"):
            if r.get("ocr_student_id") is None:
                continue
            compared += 1
            if norm(r["ocr_student_id"]) != norm(r.get("student_id")):
                items.append({"page": r.get("page"), "id_read": r["ocr_student_id"], "id_final": r.get("student_id")})
    else:
        return None
    summary = {"compared": compared, "changed": len(items)}
    if without_original:
        summary["without_original"] = without_original
    if diffs:
        summary["mean_abs_change"] = round(mean(diffs), 3)
    return {"summary": summary, "items": items}


# --- Running -----------------------------------------------------------------------------------

def load_env_file(path: Path) -> dict:
    """Variables of a .env file (values stripped of quotes and Windows line endings)."""
    from dotenv import dotenv_values
    return {k: (v or "").strip().strip("\"'") for k, v in dotenv_values(path).items()}


def step_environment(data, base: Path) -> dict:
    """The environment of a step: the .env variables (API keys) and the tools' bin folder first in PATH."""
    env = dict(os.environ)
    env_file = (data.get("environment") or {}).get("env_file")
    if env_file and (base / str(env_file)).exists():
        env.update(load_env_file(base / str(env_file)))
    bin_dir = (data.get("environment") or {}).get("bin")
    if bin_dir:
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return env


def run_step(path: Path, data, ref: str, yes: bool = False, unlock: bool = False, dry_run: bool = False) -> int:
    base = path.parent
    _, _, step = get_step(data, ref)
    if step.get("locked") and not unlock:
        print(f"{ref} is locked (printed or published). Pass --unlock only if the teacher asked to redo it.")
        return 2
    warnings = [w for w in rerun_warnings(step, base) if not w.startswith("locked")]
    for w in warnings:
        print(f"WARNING: {w}")
    if warnings and not yes and not dry_run:
        print("Not run. Confirm with the teacher, then pass --yes.")
        return 2
    argv = render_args(step)
    cwd = step_cwd(step, base)
    print(f"cd {shlex.quote(str(cwd))} && {shlex.join(argv)}")
    if dry_run:
        return 0
    code = subprocess.run(argv, cwd=cwd, env=step_environment(data, base)).returncode
    step["last_run"] = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "exit_code": code}
    save(path, data)
    return code


# --- Template --------------------------------------------------------------------------------

TEMPLATE = """\
# Course record for the AI4Exams tools (ptestgen, pexams, pevaluate).
# One file per course. An agent keeps it up to date after every step, and uses it to
# repeat the work next year. `ptestgen course --help` lists the commands that read it.
# Paths in a step are relative to its `cwd` (default: this folder).
# Never write API keys here: name the variable and the .env file that holds it.
schema: {schema}
course:
  name: {name}
  code:
  year: {year}
  institution:
  languages: [es]
  lms: moodle
environment:
  bin:                 # folder with the ptestgen/pexams/pevaluate executables, if not on PATH
  env_file:            # .env with the API keys (relative to this file)
  api_key_env: ANTHROPIC_API_KEY
models:                # chosen with the teacher at setup; see the skill's models-and-costs reference
  header: {{model: claude-opus-5-5, effort: low}}
  open_answers: {{model: claude-opus-5-5, effort: medium}}
  lab: {{model: claude-opus-5-5, effort: medium}}
policy: {{}}           # e.g. lab_weight: 0.3, exam_weight: 0.7, penalty, voluntary questions
roster: {{}}           # gradebook export: file, id_column, name_column, mark_column, feedback_column
assessments: {{}}
# assessments:
#   P1:
#     title: Lab 1 quiz
#     date: 2026-10-01
#     status: draft      # draft | printed | graded | published
#     weight: 10% of the course   # optional, informative only
#     questions: P1/examen/examen_P1.md
#     students: 30
#     decisions:
#       - "2026-10-02: question 3 voided nicely (ambiguous statement)."
#     steps:
#       export:
#         command: ptestgen export pexams
#         cwd: P1/examen
#         positional: [examen_P1.md]
#         args: {{num_models: 1, total_students: 30, extra_model_templates: 2, lang: es, fill_answer_space: true}}
#         output: examen_P1_pexams_output
#         locked: true   # set once printed
#       correct:
#         command: ptestgen correct pexams
#         cwd: P1/examen
#         positional: [examen_P1.md]
#         args: {{input_path: [../scans/P1.pdf], exam_dir: examen_P1_pexams_output, output_dir: correccion, api_key_env: CLAUDE_KEY}}
"""


def init(path: Path, name: str, year: str = "", force: bool = False) -> Path:
    if path.is_dir():
        path = path / FILE_NAME
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists.")
    path.write_text(TEMPLATE.format(schema=SCHEMA, name=json.dumps(name, ensure_ascii=False), year=year), encoding="utf-8")
    return path


# --- CLI -------------------------------------------------------------------------------------

def _print_overview(data, base: Path) -> None:
    print(f"{(data.get('course') or {}).get('name')}  [{data.get('schema')}]")
    for assessment_id, assessment in (data.get("assessments") or {}).items():
        assessment = assessment or {}
        weight = f"  weight={assessment['weight']}" if assessment.get("weight") else ""
        print(f"\n{assessment_id}: {assessment.get('title', '')}  status={assessment.get('status', '')}{weight}")
        for step_id, step in (assessment.get("steps") or {}).items():
            out = step_output(step, base)
            state = "done" if out is not None and out.exists() else "not run"
            lock = ", locked" if step.get("locked") else ""
            print(f"  {assessment_id}.{step_id:<14} {step.get('command', ''):<28} {state}{lock}")


def _show_step(data, base: Path, ref: str) -> None:
    _, _, step = get_step(data, ref)
    cwd = step_cwd(step, base)
    print(f"cd {shlex.quote(str(cwd))} && {shlex.join(render_args(step))}")
    out = step_output(step, base)
    if out is not None:
        print(f"output: {out}{'' if out.exists() else ' (not run yet)'}")
    for w in rerun_warnings(step, base):
        print(f"WARNING: {w}")


def handle_course(args) -> int:
    if args.course_command == "init":
        target = Path(args.path or ".")
        print(f"Created {init(target, args.name, args.year or '', args.force)}")
        return 0
    path = find_course_file(args.path)
    data = load(path)
    base = path.parent
    if args.course_command == "validate":
        issues = validate(data, base)
        for level, message in issues:
            print(f"{level.upper():8} {message}")
        errors = sum(level == "error" for level, _ in issues)
        print(f"{path}: {errors} error(s), {sum(l == 'warning' for l, _ in issues)} warning(s).")
        return 1 if errors else 0
    if args.course_command == "show":
        if args.step:
            _show_step(data, base, args.step)
        else:
            _print_overview(data, base)
        return 0
    if args.course_command == "review":
        from .course_review import review
        return review(path, args.assessment, part=args.part, port=args.port, open_browser=not args.no_browser,
                      keep_open=args.keep_open)
    if args.course_command == "run":
        return run_step(path, data, args.step, yes=args.yes, unlock=args.unlock, dry_run=args.dry_run)
    if args.course_command in ("metrics", "edits"):
        compute = step_metrics if args.course_command == "metrics" else step_edits
        refs = [args.step] if args.step else [f"{a}.{s}" for a, s, _ in iter_steps(data)]
        for ref in refs:
            _, _, step = get_step(data, ref)
            result = compute(step, base, data.get("prices")) if compute is step_metrics else compute(step, base)
            if result is None:
                continue
            if args.write:
                step[args.course_command] = result
            shown = result if compute is step_metrics else {"summary": result["summary"], "items": len(result["items"])}
            print(f"{ref}: {json.dumps(shown, ensure_ascii=False, default=str)}")
        if args.write:
            save(path, data)
            print(f"Written to {path}")
        return 0
    raise ValueError(args.course_command)


def add_parser(subparsers, parents) -> None:
    parser = subparsers.add_parser("course", parents=parents,
                                   help="Read and update the course record (ai4exams.yaml).")
    sub = parser.add_subparsers(dest="course_command", required=True)
    p = sub.add_parser("init", help="Create ai4exams.yaml from the template.")
    p.add_argument("path", nargs="?", help="Folder or file (default: current folder).")
    p.add_argument("--name", required=True, help="Course name.")
    p.add_argument("--year", help="Academic year, e.g. 2026-2027.")
    p.add_argument("--force", action="store_true", help="Overwrite an existing file.")
    for name, help_text in (("validate", "Check the file: schema, paths, API keys, steps not run."),
                            ("show", "Overview of all steps, or the exact command of one (ASSESSMENT.STEP)."),
                            ("metrics", "Compute LLM calls, tokens, cost and marks from each step's artifacts."),
                            ("edits", "List where the teacher changed the model's grade or the ID read from a scan."),
                            ("run", "Run one step (ASSESSMENT.STEP) with the .env loaded, refusing locked steps."),
                            ("review", "Open the review app of an assessment: edit grades, answers and students, rebuild marks and PDFs.")):
        p = sub.add_parser(name, help=help_text)
        if name in ("show", "metrics", "edits"):
            p.add_argument("step", nargs="?", help="ASSESSMENT.STEP (default: all).")
        if name == "run":
            p.add_argument("step", help="ASSESSMENT.STEP")
            p.add_argument("--yes", action="store_true", help="Run although outputs would be overwritten.")
            p.add_argument("--unlock", action="store_true", help="Run a locked step.")
            p.add_argument("--dry-run", action="store_true", help="Print the command only.")
        if name == "review":
            p.add_argument("assessment", help="ASSESSMENT (e.g. P1).")
            p.add_argument("--part", choices=["exam", "free", "lab"], help="When the assessment has several: the scanned exam, "
                                                                          "the blank-paper exam or the lab submissions (default: the first).")
            p.add_argument("--port", type=int, default=0, help="Port on 127.0.0.1 (default: any free port).")
            p.add_argument("--no-browser", action="store_true", help="Print the URL without opening the browser.")
            p.add_argument("--keep-open", action="store_true", help="Keep the server running when the page is closed (default: it stops).")
        if name in ("metrics", "edits"):
            p.add_argument("--write", action="store_true", help="Store the result in the step (`metrics:`/`edits:`).")
        p.add_argument("--path", help=f"Course file or folder (default: the {FILE_NAME} in this folder or above).")
    parser.set_defaults(func=lambda a: sys.exit(handle_course(a)))
