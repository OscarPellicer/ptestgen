"""``ptestgen course review ASSESSMENT``: the review app of pevaluate, configured from the course
record (result folders, exam folder, class list, penalty, voided questions) and with buttons
that rerun the assessment's own steps to rebuild marks, PDFs and upload files.

The rebuild never reads the scans again or grades with the LLM: it runs only the analysis step
(``only_analysis``) and the open-answer grading step while every answer has a saved grade, then
the steps that build the files to upload. Afterwards the teacher's edits go to the record
(``edits``), as ``ptestgen course edits --write`` would do.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .course import (get_step, load, render_args, save, step_cwd, step_edits, step_environment, step_kind,
                     step_output)

PUBLISH_KINDS = ("combine", "moodle_csv", "poliformat_zip")


def _steps(data, assessment_id: str) -> list[tuple[str, dict]]:
    assessment = (data.get("assessments") or {}).get(assessment_id)
    if assessment is None:
        raise KeyError(f"Assessment '{assessment_id}' not found. Assessments: {', '.join(data.get('assessments') or {})}")
    return [(str(s), step) for s, step in (assessment.get("steps") or {}).items()]


def _arg_path(step: dict, base: Path, key: str) -> Optional[str]:
    value = (step.get("args") or {}).get(key)
    return str((step_cwd(step, base) / str(value)).resolve()) if value else None


def _list(value) -> list[str]:
    if value in (None, "", False):
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [v.strip() for v in str(value).split(",") if v.strip()]


PART_KINDS = {"exam": ("correct_pexams", "exam_open"), "free": ("exam_free",), "lab": ("lab",)}


def review_parts(path: Path, assessment_id: str) -> list[str]:
    """The parts of an assessment with results to review: ``exam`` (scanned pexams exam and its
    open answers), ``free`` (blank-paper exam), ``lab`` (submissions)."""
    kinds = {step_kind(step) for _, step in _steps(load(path), assessment_id)}
    return [part for part, part_kinds in PART_KINDS.items() if kinds & set(part_kinds)]


def review_config(path: Path, assessment_id: str, part: Optional[str] = None):
    """A pevaluate ``ReviewConfig`` for one assessment of the course record (one part of it, when
    it has several: an exam and the lab work graded together, for example)."""
    from autocorrect.review.data import ReviewConfig

    data = load(path)
    base = path.parent
    parts = review_parts(path, assessment_id)
    if not parts:
        raise ValueError(f"{assessment_id} has no correction or grading step with results to review.")
    part = part or parts[0]
    if part not in parts:
        raise ValueError(f"{assessment_id} has no '{part}' part. Parts: {', '.join(parts)}")
    other = {k for p, ks in PART_KINDS.items() if p != part for k in ks} - set(PART_KINDS[part])
    steps = [(s, step) for s, step in _steps(data, assessment_id) if step_kind(step) not in other]
    assessment = data["assessments"][assessment_id]
    cfg = ReviewConfig(title=f"{assessment_id} · {assessment.get('title', '')}".strip(" ·"),
                       lang=((data.get("course") or {}).get("languages") or ["es"])[0])
    analysis, grading, lab, publish = None, None, None, []
    for step_id, step in steps:
        kind = step_kind(step)
        out = step_output(step, base)
        if kind == "correct_pexams":
            cfg.mc_dir = str(out) if out else cfg.mc_dir
            cfg.exam_dir = cfg.exam_dir or _arg_path(step, base, "exam_dir")
            args = step.get("args") or {}
            if args.get("penalty") is not None:
                cfg.penalty = float(args["penalty"])
            if args.get("only_analysis"):
                analysis = step_id
                cfg.mc_void = _list(args.get("void_questions"))
                cfg.mc_void_nicely = _list(args.get("void_questions_nicely"))
        elif kind in ("exam_open", "exam_free"):
            grading = step_id
            cfg.open_dir = str(out) if out else None
            cfg.exam_dir = _arg_path(step, base, "exam_dir") or cfg.exam_dir
            cfg.index_csv = _arg_path(step, base, "index_csv")
            cfg.mc_dir = _arg_path(step, base, "mc_correction_dir") or cfg.mc_dir
            args = step.get("args") or {}
            cfg.open_void = _list(args.get("void_questions"))
            cfg.open_void_nicely = _list(args.get("void_questions_nicely"))
            cfg.lang = args.get("lang") or cfg.lang
        elif kind == "lab":
            lab = step_id
            cfg.feedback_dir = str(out) if out else None
            session = step_cwd(step, base) / str((step.get("positional") or ["."])[0])
            rubric = (step.get("args") or {}).get("rubric")
            cfg.rubric = str(session / str(rubric)) if rubric else None
            cfg.base_dirs.append(str(step_cwd(step, base)))
        elif kind in PUBLISH_KINDS:
            publish.append(step_id)
            if kind == "poliformat_zip" and step.get("positional"):
                # The assignment's own download is its class list.
                cfg.roster = str(step_cwd(step, base) / str(step["positional"][0]))
        cwd = step_cwd(step, base)
        if str(cwd) not in cfg.base_dirs:
            cfg.base_dirs.append(str(cwd))
    if not cfg.roster:
        roster = data.get("roster") or {}
        roster_file = roster.get("file") if isinstance(roster, dict) else roster
        if roster_file and (base / str(roster_file)).exists():
            cfg.roster = str(base / str(roster_file))
            if isinstance(roster, dict):
                cfg.roster_id_column, cfg.roster_name_column = roster.get("id_column"), roster.get("name_column")
    if not (cfg.mc_dir or cfg.open_dir or cfg.feedback_dir):
        raise ValueError(f"{assessment_id} has no correction or grading step with results to review.")
    cfg.rebuild_actions = _actions(path, cfg, assessment_id, analysis, grading, lab, publish)
    return cfg


PART_LABELS = {"es": {"exam": "Examen (hoja impresa)", "free": "Examen (folio en blanco)", "lab": "Prácticas"},
               "en": {"exam": "Exam (printed sheet)", "free": "Exam (blank paper)", "lab": "Lab work"}}


def review_configs(path: Path, assessment_id: str) -> list[tuple]:
    """Every part of the assessment as ``(part, label, ReviewConfig)``, for one app with a part
    selector. Rebuilding the upload files first rebuilds the marks of every part (saved grades,
    no LLM), so the combination never reads stale marks."""
    parts = [(part, review_config(path, assessment_id, part)) for part in review_parts(path, assessment_id)]
    if len(parts) > 1:
        marks = [a for _, cfg in parts for a in cfg.rebuild_actions if a.id == "marks"]
        for _, cfg in parts:
            upload = next((a for a in cfg.rebuild_actions if a.id == "upload"), None)
            if upload is None or not marks:
                continue

            def run_all(publish=upload.run):
                log = []
                for action in marks:
                    ok, output = action.run()
                    log.append(output)
                    if not ok:
                        return False, "\n\n".join(log)
                ok, output = publish()
                return ok, "\n\n".join(log + [output])
            upload.run = run_all
            upload.description = " → ".join([a.description.split(" (")[0] for a in marks] + [upload.description])
    labels = PART_LABELS.get(parts[0][1].lang, PART_LABELS["en"]) if parts else {}
    return [(part, labels.get(part, part), cfg) for part, cfg in parts]


def _run(path: Path, ref: str) -> tuple[bool, str]:
    """Run one step as `ptestgen course run` does, capturing its output for the page."""
    data = load(path)
    base = path.parent
    _, _, step = get_step(data, ref)
    if step.get("locked"):
        return False, f"{ref} is locked (printed or published): not run."
    argv = render_args(step)
    result = subprocess.run(argv, cwd=step_cwd(step, base), env=step_environment(data, base), capture_output=True, text=True)
    step["last_run"] = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "exit_code": result.returncode}
    save(path, data)
    return result.returncode == 0, f"$ {' '.join(argv)}\n{(result.stdout + result.stderr)[-4000:]}"


def _record_edits(path: Path, refs: list[str]) -> None:
    data = load(path)
    for ref in refs:
        _, _, step = get_step(data, ref)
        result = step_edits(step, path.parent)
        if result is not None:
            step["edits"] = result
    save(path, data)


def _actions(path: Path, cfg, assessment_id: str, analysis, grading, lab, publish) -> list:
    from autocorrect.review.data import RebuildAction
    from autocorrect.review.server import open_answers_pending

    es = cfg.lang == "es"
    ref = lambda step_id: f"{assessment_id}.{step_id}"
    graded = [ref(s) for s in (grading, lab, analysis) if s]
    # Every saved edit goes to the course record at once (``edits`` of the graded steps).
    cfg.on_edit = lambda: _record_edits(path, graded)
    actions = []
    rebuild_steps = [ref(s) for s in (analysis, grading) if s]
    if rebuild_steps:
        def rebuild():
            pending = open_answers_pending(cfg)
            if pending:
                return False, (f"{len(pending)} answer(s) without a saved grade ({', '.join(pending[:5])}...): the "
                               f"grading step would call the LLM. Run {ref(grading)} first.")
            log = []
            for step_ref in rebuild_steps:
                ok, output = _run(path, step_ref)
                log.append(output)
                if not ok:
                    return False, "\n\n".join(log)
            _record_edits(path, graded)
            return True, "\n\n".join(log)
        actions.append(RebuildAction("marks", "Reconstruir notas y PDF" if es else "Rebuild marks and PDFs",
                                     " → ".join(rebuild_steps) + " (no LLM calls)", rebuild))
    if publish:
        def build_uploads():
            log = []
            for step_ref in [ref(s) for s in publish]:
                ok, output = _run(path, step_ref)
                log.append(output)
                if not ok:
                    return False, "\n\n".join(log)
            _record_edits(path, graded)
            return True, "\n\n".join(log)
        actions.append(RebuildAction("upload", "Reconstruir ficheros para subir" if es else "Rebuild upload files",
                                     " → ".join(ref(s) for s in publish), build_uploads))
    return actions


def review(path: Path, assessment_id: str, part: Optional[str] = None, port: int = 0, open_browser: bool = True,
           keep_open: bool = False) -> int:
    from autocorrect.review.server import serve

    parts = review_configs(path, assessment_id)
    if part and part not in [p for p, _, _ in parts]:
        raise ValueError(f"{assessment_id} has no '{part}' part. Parts: {', '.join(p for p, _, _ in parts)}")
    serve(parts=parts, initial=part, port=port, open_browser=open_browser, keep_open=keep_open)
    return 0
