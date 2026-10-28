import json

import pytest
import yaml

from ptestgen import agent_skill, course


def _write_course(tmp_path, steps):
    data = {"schema": course.SCHEMA, "course": {"name": "Test"}, "environment": {"env_file": "keys.env"},
            "assessments": {"P1": {"title": "Quiz", "steps": steps}}}
    path = tmp_path / course.FILE_NAME
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_init_creates_a_valid_template(tmp_path):
    path = course.init(tmp_path, "Salud", "2026-2027")
    data = course.load(path)
    assert data["schema"] == course.SCHEMA and data["course"]["name"] == "Salud"
    assert not [i for i in course.validate(data, tmp_path) if i[0] == "error"]
    with pytest.raises(FileExistsError):
        course.init(tmp_path, "Salud")


def test_render_args_and_output(tmp_path):
    step = {"command": "ptestgen correct pexams", "cwd": "exam", "positional": ["q.md"],
            "args": {"input_path": ["a.pdf", "b.pdf"], "exam_dir": "out", "output_dir": "corr", "only_analysis": True,
                     "simplify_csv": False, "penalty": 0.25}}
    assert course.render_args(step) == ["ptestgen", "correct", "pexams", "q.md", "--input-path", "a.pdf", "b.pdf",
                                        "--exam-dir", "out", "--output-dir", "corr", "--only-analysis", "--penalty", "0.25"]
    assert course.step_output(step, tmp_path) == (tmp_path / "exam" / "corr").resolve()
    lab = {"command": "pevaluate", "positional": ["lab1"], "args": {"rubric": "r.txt"}}
    assert course.step_kind(lab) == "lab" and course.step_output(lab, tmp_path) == (tmp_path / "lab1" / "feedback").resolve()


def test_validate_flags_missing_inputs_and_pasted_keys(tmp_path):
    path = _write_course(tmp_path, {"correct": {"command": "ptestgen correct pexams", "args": {"exam_dir": "nowhere", "output_dir": "c"}}})
    issues = course.validate(course.load(path), tmp_path)
    assert any(level == "warning" and "exam_dir not found" in msg for level, msg in issues)
    assert any(level == "info" and "not run yet" in msg for level, msg in issues)
    path.write_text(path.read_text() + "# sk-ant-api03-abcdefghijklmnopqrstuvwxyz\n")
    assert any(level == "error" and "API key" in msg for level, msg in course.validate(course.load(path), tmp_path))


def test_rerun_warnings_and_locked_run(tmp_path, capsys):
    (tmp_path / "out").mkdir()
    steps = {"export": {"command": "ptestgen export pexams", "positional": ["q.md"], "output": "out", "locked": True},
             "grade": {"command": "pevaluate exam-open", "args": {"output_dir": "out", "force_regrade": True}}}
    path = _write_course(tmp_path, steps)
    data = course.load(path)
    assert course.run_step(path, data, "P1.export") == 2
    assert "locked" in capsys.readouterr().out
    assert course.run_step(path, data, "P1.grade") == 2  # would discard the teacher's edits
    assert course.run_step(path, data, "P1.grade", dry_run=True) == 0
    assert "pevaluate exam-open --output-dir out --force-regrade" in capsys.readouterr().out


def test_run_loads_env_without_printing_it(tmp_path, capfd):
    (tmp_path / "keys.env").write_text("SECRET_KEY='abc123'\r\n")
    script = tmp_path / "check.py"
    script.write_text("import os, sys; sys.exit(0 if os.environ.get('SECRET_KEY') == 'abc123' else 3)")
    path = _write_course(tmp_path, {"check": {"command": "pevaluate", "positional": []}})
    data = course.load(path)
    data["assessments"]["P1"]["steps"]["check"]["command"] = "pevaluate"
    import sys
    step = data["assessments"]["P1"]["steps"]["check"]
    step["command"] = f"{sys.executable} check.py"
    assert course.run_step(path, data, "P1.check", yes=True) == 0
    assert "abc123" not in capfd.readouterr().out
    assert course.load(path)["assessments"]["P1"]["steps"]["check"]["last_run"]["exit_code"] == 0


def _exam_open_output(folder):
    folder.mkdir(parents=True)
    grader = {"model": "claude-opus-5-5", "effort": "medium"}
    responses = [
        {"student_id": "1", "question_id": "1", "original_id": "q_a", "score": 1.0, "feedback": "Correcto.",
         "grader": {**grader, "score": 0.5, "feedback": "Falta X."}},
        {"student_id": "2", "question_id": "1", "original_id": "q_a", "score": 1.0, "feedback": "Correcto.",
         "grader": {**grader, "score": 1.0, "feedback": "Correcto."}},
        {"student_id": "3", "question_id": "1", "original_id": "q_a", "score": 0.0, "feedback": "x", "grader": grader},
    ]
    (folder / "open_evaluations.yaml").write_text(yaml.safe_dump({"responses": responses}), encoding="utf-8")
    with open(folder / "open_scores.csv", "w", encoding="utf-8") as f:
        f.write("student_id,question_id,score,max_score,status\n1,1,1,1,cached\n2,1,1,1,cached\n3,1,0,1,graded\n")
    calls = [{"model_served": "claude-opus-5-5", "effort": "medium", "purpose": "grade_open_answer", "fallback_used": False,
              "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000}, "latency_s": 2.0, "timestamp_utc": "2026-10-27T10:00:00+00:00"}] * 2
    (folder / "llm_calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in calls), encoding="utf-8")
    (folder / "run_manifest.json").write_text(json.dumps({"started_utc": "2026-10-27T10:00:00+00:00",
        "llm": {"model": "claude-opus-5-5", "effort": "medium"},
        "packages": {"pevaluate": {"version": "0.2.0", "git_commit": "abc"}, "anthropic": {"version": "1"}}}), encoding="utf-8")


def test_metrics_and_edits_are_written_to_the_record(tmp_path):
    _exam_open_output(tmp_path / "open")
    path = _write_course(tmp_path, {"grade": {"command": "pevaluate exam-open", "args": {"output_dir": "open"}}})
    data = course.load(path)
    _, _, step = course.get_step(data, "P1.grade")
    metrics = course.step_metrics(step, tmp_path)
    assert metrics["llm"]["calls"] == 2 and metrics["llm"]["cost_usd"] == 2 * (4.0 + 2.0)
    assert metrics["run"]["packages"] == {"pevaluate": "0.2.0 (abc)"}
    assert metrics["students"] == 3 and metrics["mark"]["mean"] == pytest.approx(6.667, abs=1e-3)
    edits = course.step_edits(step, tmp_path)
    assert edits["summary"] == {"compared": 2, "changed": 1, "without_original": 1, "mean_abs_change": 0.5}
    assert edits["items"] == [{"student_id": "1", "question": "q_a", "llm_score": 0.5, "score": 1.0, "feedback": "Correcto."}]

    import argparse  # CLI path: --write keeps the comments of the file
    args = argparse.Namespace(course_command="edits", path=str(path), step=None, write=True)
    path.write_text("# keep me\n" + path.read_text(), encoding="utf-8")
    course.handle_course(args)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# keep me") and "mean_abs_change: 0.5" in text


def test_lab_and_scan_edits(tmp_path):
    feedback = tmp_path / "lab" / "feedback"; feedback.mkdir(parents=True)
    (feedback / "feedback_a.yaml").write_text(yaml.safe_dump({"mark": 8.0, "feedback": "ok", "source_id": "s1",
                                                              "grader": {"mark": 7.0, "feedback": "ok"}}))
    corr = tmp_path / "corr"; corr.mkdir()
    (corr / "correction_results.csv").write_text("page,student_id,ocr_student_id\n1,12345678A,12345678A\n3,87654321B,8765432IB\n")
    lab = {"command": "pevaluate", "positional": ["lab"]}
    scan = {"command": "ptestgen correct pexams", "args": {"output_dir": "corr"}}
    assert course.step_edits(lab, tmp_path)["items"] == [{"submission": "s1", "llm_mark": 7.0, "mark": 8.0}]
    edits = course.step_edits(scan, tmp_path)
    assert edits["summary"] == {"compared": 2, "changed": 1}
    assert course.step_metrics(scan, tmp_path)["id_read_differs_from_final"] == 1


def test_skill_install_and_agents_text(tmp_path):
    target = agent_skill.install(tmp_path / "skills" / "ptestgen")
    assert (target / "SKILL.md").exists() and (target / "references" / "course-yaml.md").exists()
    agent_skill.install(target)  # reinstalling over our own copy is fine
    other = tmp_path / "other"; other.mkdir()
    with pytest.raises(FileExistsError):
        agent_skill.install(other)
    text = agent_skill.agents_text()
    assert text.startswith("---\nname: ptestgen") and "ptestgen skill install" in text


def test_skill_references_exist():
    skill = (agent_skill.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for name in ("question-format", "exam-pdf", "correction", "models-and-costs", "course-yaml", "pitfalls"):
        assert f"references/{name}.md" in skill
        assert (agent_skill.SKILL_DIR / "references" / f"{name}.md").exists()


def test_poliformat_zip_steps_are_recognised_and_warn_on_rerun(tmp_path):
    from ptestgen.course import rerun_warnings, step_kind

    (tmp_path / "upload.zip").write_bytes(b"zip")
    step = {"command": "pevaluate poliformat-zip", "positional": ["download.zip"],
            "args": {"marks": "overall_marks.csv", "output": "upload.zip"}}
    assert step_kind(step) == "poliformat_zip"
    assert any("PoliformaT" in w for w in rerun_warnings(step, tmp_path))


def test_review_config_from_the_course_record(tmp_path):
    from ptestgen.course_review import review_config

    (tmp_path / "exam" / "out").mkdir(parents=True)
    (tmp_path / "exam" / "corr").mkdir()
    (tmp_path / "exam" / "open").mkdir()
    (tmp_path / "exam" / "Tarea_20260101.zip").write_bytes(b"")
    steps = {
        "correct": {"command": "ptestgen correct pexams", "cwd": "exam", "positional": ["e.md"],
                    "args": {"input_path": ["scans"], "exam_dir": "out", "output_dir": "corr", "penalty": 0.25}},
        "analysis": {"command": "ptestgen correct pexams", "cwd": "exam", "positional": ["e.md"],
                     "args": {"exam_dir": "out", "output_dir": "corr", "only_analysis": True, "void_questions_nicely": "11"}},
        "grade_open": {"command": "pevaluate exam-open", "cwd": "exam",
                       "args": {"index_csv": "corr/open_responses_index.csv", "exam_dir": "out", "output_dir": "open",
                                "mc_correction_dir": "corr", "void_questions_nicely": "26", "lang": "es"}},
        "publish": {"command": "pevaluate poliformat-zip", "cwd": "exam", "positional": ["Tarea_20260101.zip"],
                    "args": {"marks": "open/overall_marks.csv", "output": "subir.zip"}},
    }
    path = _write_course(tmp_path, steps)
    cfg = review_config(path, "P1")
    assert cfg.mc_dir.endswith("corr") and cfg.open_dir.endswith("open") and cfg.exam_dir.endswith("out")
    assert cfg.penalty == 0.25 and cfg.mc_void_nicely == ["11"] and cfg.open_void_nicely == ["26"]
    assert cfg.roster.endswith("Tarea_20260101.zip")  # the assignment's download is its class list
    # Rebuilding never reruns the step that reads the scans.
    assert [(a.id, a.description) for a in cfg.rebuild_actions] == [
        ("marks", "P1.analysis → P1.grade_open (no LLM calls)"), ("upload", "P1.publish")]


def test_review_parts_and_chained_upload(tmp_path):
    from ptestgen.course_review import review_configs, review_parts

    for folder in ("exam/out", "exam/corr", "exam/open", "lab/feedback"):
        (tmp_path / folder).mkdir(parents=True)
    steps = {
        "correct": {"command": "ptestgen correct pexams", "cwd": "exam", "args": {"exam_dir": "out", "output_dir": "corr"}},
        "grade_open": {"command": "pevaluate exam-open", "cwd": "exam",
                       "args": {"index_csv": "corr/i.csv", "exam_dir": "out", "output_dir": "open", "mc_correction_dir": "corr"}},
        "grade_lab": {"command": "pevaluate", "cwd": "lab", "positional": ["."], "args": {"rubric": "rubric.txt"}},
        "combine": {"command": "pevaluate combine-marks", "cwd": ".", "args": {"lab_feedback": "lab/feedback", "output": "notas.csv"}},
    }
    path = _write_course(tmp_path, steps)
    assert review_parts(path, "P1") == ["exam", "lab"]
    parts = review_configs(path, "P1")
    assert [(p, label) for p, label, _ in parts] == [("exam", "Examen (hoja impresa)"), ("lab", "Prácticas")]  # the course language (default es)
    exam_cfg, lab_cfg = parts[0][2], parts[1][2]
    assert exam_cfg.open_dir.endswith("open") and not exam_cfg.feedback_dir
    assert lab_cfg.feedback_dir.endswith("feedback") and not lab_cfg.open_dir
    # The upload files are rebuilt after the marks of every part, from either part.
    upload = {a.id: a for a in lab_cfg.rebuild_actions}["upload"]
    assert upload.description == "P1.grade_open → P1.combine"
