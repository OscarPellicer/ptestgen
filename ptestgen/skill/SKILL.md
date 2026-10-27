---
name: ptestgen
description: Create, print, correct and grade exams and assignments with ptestgen, pexams and pevaluate. Use when the user wants to write or generate exam questions, make printable exam PDFs (multiple choice and/or open answers), correct scanned exams, grade open answers, blank-paper exams or lab notebooks with an LLM, void questions, combine marks into a gradebook, upload marks and feedback to the LMS (Moodle, PoliformaT/Sakai), or reuse a previous year's exams.
---

# Exams with ptestgen, pexams and pevaluate

Three Python packages, installed together with `pip install ptestgen`:

| Package | Does |
|---|---|
| `ptestgen` | Questions in Markdown (written by you or generated from course material with an LLM), export to PDF / Moodle / Wooclap, scan correction, statistics per question. The entry point; also holds this skill and the course record. |
| `pexams` | Exam PDFs with answer sheets and open-answer boxes, reading the scans (bubbles, fiducial marks, ID/name boxes via an LLM), marks and statistics. |
| `pevaluate` | LLM grading of open answers (from the scan crops or from blank-paper scans) and of submissions (notebooks, PDFs), mark combination, Moodle and PoliformaT (Sakai) upload files. |

**You operate the tools; the teacher decides.** Never ask the teacher to run a command. Explain in plain words what can be done, what it costs and what it changes; when they agree, run it yourself and report the result. The teacher only does what needs hands or eyes: printing, scanning, downloading from the LMS, uploading marks, and reviewing what you show them. If they want to edit a file themselves (the questions, a grade), tell them which file and which fields.

## Rules

- **Course record first.** Every course has one `ai4exams.yaml` (see `references/course-yaml.md`). Read it before doing anything; if there is none, create it with `ptestgen course init`. After every step, record the launch configuration (command, args, cwd, output), decisions (voided questions, policies, exceptions) and status. `ptestgen course show` prints the overview and the exact command of a step; `ptestgen course run A.S` runs it with the `.env` loaded.
- **Never overwrite silently.** Before rerunning a step, read its warnings (`ptestgen course show A.S`). An exam that was printed is `locked: true`: re-exporting it would make the scans unreadable. `--force-regrade` discards the teacher's edits. Ask first.
- **API keys.** Never print, log or write a key, and never ask the teacher to paste one in the chat. Keys live in a `.env` file outside any repository; the course record names only the file and the variable.
- **Personal data.** Scans and submissions contain names and IDs; they go to the LLM provider only because the teacher chose to grade with it. Keep the course record and outputs in the course's private folder, never in a public repository.
- **Costs.** Before a step with LLM calls, give the estimated cost (`references/models-and-costs.md`). After it, `ptestgen course metrics A.S` gives the real one.
- **Long runs.** Prevent sleep during LLM runs (macOS: prefix `caffeinate -i`; Linux: `systemd-inhibit`). A request in flight while the machine sleeps blocks the run.

## 0. Setup (first time on a machine or course)

Do this yourself and tell the teacher what you did.

1. **Python environment.** Look for one that already has the tools (`pip show ptestgen`, `conda env list`). Otherwise create one (Python 3.11 recommended) and `pip install ptestgen` (installs pexams and pevaluate). Record the folder of its executables as `environment.bin` in the course record.
2. **Browser for PDFs.** `python -m playwright install chromium`.
3. **Poppler** (reads scanned PDFs): check `pdftoppm -v`. If missing: macOS `brew install poppler`; Linux `sudo apt install poppler-utils`; Windows or no admin rights `conda install -c conda-forge poppler`.
4. **PDF check:** `pexams generate --input-file sample_test.md --to pexams --output-dir <tmp> --num-models 2 --generate-fakes 4` (the bundled sample) makes the PDFs and simulated scans. (`pexams test` only works from a clone of the repository: it runs its test suite.)
5. **API keys.** Explain to the teacher:
   - Grading and reading scans use an LLM. Recommended: Claude through the Anthropic API (a key from console.anthropic.com → API keys, with some prepaid credit). Other models go through OpenRouter (`OPENROUTER_API_KEY`).
   - They write the key into a `.env` file (e.g. `ANTHROPIC_API_KEY=...`) in a private folder outside any repository; you create the empty file and tell them where. Any variable name works (`--api-key-env NAME`).
   - Check that it loads without printing it: `python -c "import os; from dotenv import load_dotenv; load_dotenv('<path>'); print(bool(os.getenv('<NAME>')))"`.
   - Record `environment.env_file` and `environment.api_key_env`.
   - Then finish the smoke test: `pexams correct --input-path <tmp>/simulated_scans --exam-dir <tmp> --output-dir <tmp>/corr --api-key-env <NAME>` (a few cents). Every page should be read with its ID and name. Correction needs the key (or `pip install "pexams[trocr]"` and `--id-reader trocr`, less reliable).
6. **Models.** Show the teacher the table in `references/models-and-costs.md` (our measurements are limited: one course, two sessions) and ask them to choose. Default: Claude Opus 5.5 at medium effort for grading and at low effort for reading the exam headers. Record the choice in `models`.
7. **Course record:** `ptestgen course init --name "<course>" --year <year>` in the course folder, then fill in languages, LMS, roster (gradebook export) and policy as you learn them.

## 1. Questions

Ask: topic and material (slides, notes, last year's exam), question types (multiple choice, open answer or both), how many, languages, duration, points per question, penalty for wrong multiple-choice answers.

- **Write them yourself** from the material when the exam is short or needs care (open questions with expected answer and rubric). Format: `references/question-format.md`.
- **Generate them** with `ptestgen generate` (generator → reviewer → optional evaluator) for larger multiple-choice banks; it writes the `.md` and a `.tsv` that tracks every question's history.
- **Reuse:** last year's course record says where the exams and their statistics are (`.tsv`: answer distribution and difficulty per question).

Then tell the teacher where the `.md` is and how to edit it: one `## id {attributes}` block per question; for multiple choice the first option is the correct one (it is shuffled in the PDF); `**Explanation:**`, `**Expected answer:**` and `**Rubric:**` are not printed but used for feedback and grading. Offer to make the changes they describe.

## 2. Exam PDFs (before printing)

Ask, before exporting:
- **How many students** (`total_students`): builds `all_exams.pdf`, one copy per student, alternating the models, ready to print.
- **How many models** (`num_models`): versions with shuffled questions and options, against copying. Open-answer-only exams usually use 1.
- **Spare answer sheets** per model (`extra_model_templates`, multiple choice only): for students who spoil theirs.
- Title, course, date, language of the printed labels (`lang`), instructions (duration, penalty, allowed material; `custom_header`), columns, font size, points shown, total multiple-choice points.

Run the export (`references/exam-pdf.md`), then render the pages to images and check them yourself: page count, no question cut, boxes large enough, images and formulas visible. Tell the teacher where the PDFs are (`<questions>_pexams_output/exam_model_N.pdf`, `all_exams.pdf`) and ask them to look. Optionally simulate scans (`generate_fakes`) and correct them to test the pipeline before the exam.

When the teacher says it has been printed: set `locked: true` and `status: printed`, and record the printed PDF and the number of copies.

## 3. Scanning

Tell the teacher: 300 dpi, grayscale (never black-and-white), PDF. All exams in one batch or several PDFs (they are read in name order, an exam may span two files). Exams written on blank paper can be graded too.

## 4. Correction and grading

Which path (`references/correction.md`):
- **Printed pexams exams** → `ptestgen correct pexams` (reads model, ID and name with the LLM, the bubbles, matches the class list, marks, statistics, crops every open answer) → `pevaluate exam-open` for the open answers (with `mc_correction_dir` for mixed exams: one final mark per student in `overall_marks.csv`).
- **Blank paper** → `pevaluate exam-free` (one call per exam; answers matched to questions by content).
- **Submissions** (notebooks, PDFs) → `pevaluate <folder>` with a rubric.

After each step, tell the teacher where to look and summarise: marks (mean, distribution), students not matched to the class list, multiple-choice rows with two boxes filled (`multiple_marks` in `correction_results.csv`), the answers in `needs_review.csv` (not graded, crop off the box, writing outside the box, low confidence, blank or cut text), questions that look wrong (statistics: nobody right, or the best students wrong). Generate the student PDFs in the students' language (`lang`).

Then offer the review, showing crops and grades side by side as they ask (for text that may continue outside a box, show the context crop or the scan page):
- **Wrong ID or answer read from a scan:** fix `correction_results.csv`, rerun with `only_analysis` (it redraws the annotated sheets), then `exam-open` again.
- **Void a question:** `void_questions` removes it for everyone; `void_questions_nicely` counts it only for students it helps. Multiple choice: in `correct pexams` with `only_analysis`; open answers: in `exam-open` (no new LLM calls). Record it under `decisions`.
- **Change a grade or feedback:** edit the top-level `score`/`feedback` in `open_evaluations.yaml` (or `mark`/`feedback` in a submission's feedback YAML); never edit the `grader` block, which keeps the model's original. Rerun the same step without `force_regrade` to rebuild reports and PDFs.
- **Feedback is impersonal, in the passive voice** ("se justifica bien el umbral", "the model is not evaluated"), never "you" or "the student"; the grading prompts ask for it, and your own edits must follow it.
- **Feedback is read by students as the teacher's:** never mention scans, images, boxes, transcriptions, legibility, a review or automatic grading, also in your own edits (the reason for a change goes to `decisions`, not to the feedback). A blank answer gets no feedback. Keep it short: a full-score item gets only its score (no explanation of why it is right); explain only the deductions, in one or two concrete sentences. Ask for this in rubrics and example feedback too, and trim it in your own edits.
- When the review is done: `ptestgen course edits --write` stores in the record where the teacher changed the model's grade (only the differences), and `ptestgen course metrics --write` the calls, tokens, cost and marks.

## 5. Marks to the LMS

Ask how marks combine (weights of each part, a missing part counts 0?, a student in two submissions?). `pevaluate combine-marks` computes the final mark and a feedback text per student. Moodle assignments only accept a **grading worksheet CSV** (marks + comments) and a **feedback files zip** (attachments): ask the teacher to download each assignment's grading worksheet and fill them with `pevaluate moodle-csv --marks` (each student goes to the assignment where they or their partner submitted). `pexams moodle-feedback-zip` packs each student's corrected scan. A **PoliformaT** (UPV, Sakai) assignment takes grades, comments and PDFs in one zip: ask the teacher for the assignment's *Descargar todo* zip (it is also the class list, with DNIs) and build the *Subir todo* zip with `pevaluate poliformat-zip`; show them the match table. Tell the teacher which file to upload where (`references/correction.md`, with screenshots). Then `status: published`, and lock the steps whose output was published.

## 6. Next year, and the paper

The course record is the memory: commands, files, decisions, metrics and teacher edits. Next year, read it, copy the assessments to reuse, and change only dates, paths and what the teacher asks. For a report on the tools, `ptestgen course metrics` and `edits` give cost, time, marks and human-vs-LLM agreement per step; each output folder also holds `run_manifest.json` and `llm_calls.jsonl`.

## References

- `references/question-format.md`: the Markdown question format.
- `references/exam-pdf.md`: export options and outputs, checking the PDF.
- `references/correction.md`: correction and grading commands, outputs, editing, voiding, combining.
- `references/models-and-costs.md`: models, effort and measured costs.
- `references/course-yaml.md`: the course record and the `ptestgen course` commands.
- `references/pitfalls.md`: problems already met and how to avoid them.
