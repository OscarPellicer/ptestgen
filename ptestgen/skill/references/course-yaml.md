# The course record: `ai4exams.yaml`

One file per course, in the course's private folder. It says exactly how the tools were used: launch configuration of every step, paths to the artifacts, decisions, and (computed) metrics and teacher edits. Keep it current after every step; next year it is the starting point.

## Commands

| Command | Does |
|---|---|
| `ptestgen course init [folder] --name "Course" --year 2026-2027` | Creates the file from a commented template. |
| `ptestgen course validate` | Schema, paths, steps not run, API keys pasted by mistake. Run after editing. |
| `ptestgen course show [A.S]` | Overview of all steps (done / not run / locked), or the exact command, output and rerun warnings of one step. |
| `ptestgen course run A.S [--dry-run] [--yes] [--unlock]` | Runs a step from its folder with the `.env` loaded. Refuses locked steps, and steps whose rerun overwrites something unless `--yes` (ask the teacher first). Records `last_run`. |
| `ptestgen course metrics [A.S] [--write]` | From each step's artifacts: model and versions, LLM calls, tokens, cost, latency, fallbacks, students, marks. |
| `ptestgen course edits [A.S] [--write]` | Where the final grade differs from the model's (open answers, submissions) and where the ID read from a scan was corrected. Only the differences are stored. |

All commands find the file in the current folder or its parents (`--path` to give it).

## Schema (`ai4exams-course/1`)

```yaml
schema: ai4exams-course/1
course: {name: Health Data Analytics, code: "12345", year: 2026-2027, institution: Universitat de València,
         languages: [es, en], lms: moodle}      # lms: moodle | poliformat (UPV, Sakai) | ...
environment:
  bin: /opt/miniconda3/envs/ai4exams/bin     # executables, if not on PATH
  env_file: ../data/.env                     # relative to this file; never the key itself
  api_key_env: CLAUDE_KEY
models:
  header: {model: claude-opus-5-5, effort: low}
  open_answers: {model: claude-opus-5-5, effort: medium}
  lab: {model: claude-opus-5-5, effort: medium}
policy:                                      # free-form, in words or keys
  final_mark: 0.3 notebook + 0.7 exam; a missing part counts 0
  notebooks: graded on code completeness only; discussion questions voluntary
roster: {file: gradebook.xlsx, id_column: "ID number", name_column: Name, mark_column: Mark, feedback_column: Feedback}
prices: {}                                   # optional: model: [input, output, cache_read] USD per million tokens
assessments:
  P1:
    title: Lab 1 quiz
    date: 2026-10-01
    status: published                        # draft | printed | graded | published
    questions: P1/exam/exam_P1.md
    students: 30
    decisions:
      - "2026-10-08: question 2 voided nicely (ambiguous)."
      - "2026-10-08: student 12345678 has two submissions; the higher mark is kept."
    steps:
      export:
        command: ptestgen export pexams
        cwd: P1/exam                         # paths below are relative to it
        positional: [exam_P1.md]
        args: {exam_title: "Lab 1 quiz", num_models: 1, total_students: 30, lang: es,
               custom_header: header.md, fill_answer_space: true}
        output: exam_P1_pexams_output
        printed: {pdf: exam_P1_pexams_output/all_exams.pdf, copies: 30}
        locked: true
      correct:
        command: ptestgen correct pexams
        cwd: P1/exam
        positional: [exam_P1.md]
        args: {input_path: [../scans/P1.pdf], exam_dir: exam_P1_pexams_output, output_dir: correction,
               api_key_env: CLAUDE_KEY}
      grade_open:
        command: pevaluate exam-open
        cwd: P1/exam
        args: {index_csv: correction/open_responses_index.csv, exam_dir: exam_P1_pexams_output,
               output_dir: correction/open, model: claude-opus-5-5, effort: medium, api_key_env: CLAUDE_KEY,
               void_questions_nicely: "2"}
      grade_lab:
        command: pevaluate
        cwd: P1
        positional: [lab]
        args: {rubric: lab/rubric.txt, example: lab/example.txt, no_reference: true,
               files_regex: '.*\.(ipynb|html)$', api_key_env: CLAUDE_KEY}
      combine:
        command: pevaluate combine-marks
        cwd: P1
        args: {lab_feedback: lab/feedback, exam_scores: [exam/correction/open/open_scores.csv],
               output: marks_P1.csv, lab_weight: 0.3, exam_weight: 0.7,
               roster: ../gradebook.xlsx, roster_output: gradebook_P1.xlsx}
        locked: true                         # uploaded to the LMS
```

Rules for steps:
- `command` is the tool and subcommand; `positional` the positional arguments; `args` one entry per option (`snake_case` → `--snake-case`; `true` → bare flag; `false`/null → omitted; a list → several values).
- `output` is the folder (or file) the step writes; when omitted it is taken from `output_dir`/`output`, or `<folder>/feedback` for submission grading.
- Write the arguments actually used, including defaults that matter for replication (model, effort, penalty, voids). If a run differed from the record, fix the record.
- `locked: true` once printed or published. `printed`, `last_run`, `metrics`, `edits` are filled in as the work progresses (the last three by the commands).
- Per-student exceptions go in `decisions`, by ID. Teacher grade changes are not written by hand: `ptestgen course edits --write` stores them as differences from the model's grade (the model's original stays in each `grader` block of the output files).
- One-off steps outside the tools (a scan of a late exam, a manual merge) also get a `decisions` line with the file they produced.
