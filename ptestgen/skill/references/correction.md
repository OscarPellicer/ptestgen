# Correction and grading

All LLM steps take `--api-key-env NAME` (the variable with the key), `--model` and `--effort`. Bare `claude-...` model ids use the Anthropic API; any other id (e.g. `google/gemini-3.8-flash`) goes through OpenRouter. Every output folder gets `run_manifest.json` (command, versions, model, input hashes) and `llm_calls.jsonl` (one line per call: model served, tokens, latency, hashes).

## Printed exams: `ptestgen correct pexams`

```bash
ptestgen correct pexams exam.md --input-path scans/ --exam-dir exam_pexams_output --output-dir correction \
    --penalty 0.33333 --api-key-env ANTHROPIC_API_KEY \
    [--input-csv roster.xlsx --id-column "ID" --name-column "Name" --mark-column "Mark"]
```

- `--input-path`: one or more PDFs or folders, read in order as one batch.
- `--exam-dir`: the folder that produced the **printed** PDF.
- `--penalty`: fraction of a question's points subtracted per wrong multiple-choice answer (blank: 0).
- Headers (model, ID, name) are read by an LLM (`--id-reader llm`, default model Opus 5.5 at low effort, ~$0.002/exam). `--id-reader trocr` is local and much less reliable.
- With a class list (`--input-csv`), exams are matched by ID then name (`--name-match-threshold`); if some cannot be matched, `student_matches.csv` is written and the run stops: fix the IDs and rerun.
- `--void-questions 3,7` (numbers in the exam) / `--void-questions-nicely 11` (counted only for students it helps), with `--only-analysis` to recompute without reading the scans again. `--lang es` labels the voided questions "ANULADA" on the sheets.
- **Two boxes filled in one question** (a student crossed one out instead of using correction fluid): the question is left blank and the LLM is shown the row to say which is the final answer; the result is in the `multiple_marks` column (`5:B+C->B`, or `->?` if unresolved, which stays blank). Check every row with `->?`, and glance at the resolved ones.
- Every `--only-analysis` run **redraws the annotated sheets** from `correction_results.csv` (answers, ID, name, voids), so a fixed answer also shows on the student's sheet.
- Also updates the statistics in `exam.tsv`.

Outputs (`correction/`):

| File | Content |
|---|---|
| `correction_results.csv` | One row per exam: page, student ID/name (final and as read: `ocr_student_id`, `ocr_student_name`), model, answer per question. Edit it to fix a misread ID or answer, then rerun with `--only-analysis`. |
| `final_marks.csv` | Multiple-choice score, correct/incorrect/blank and mark /10 per student. |
| `question_stats.csv`, `stats_report.pdf` | Per question: answer distribution, difficulty, discrimination; marks histogram. |
| `scanned_pages/` | Each exam's annotated answer sheet, named by student (the unannotated sheet in `scanned_pages/.raw/`, redrawn from at every analysis). `_scanned_pages_unmatched/`, `debug/`: pages not identified, detection images. |
| `open_responses/`, `open_responses_index.csv` | One crop per open answer. The index has `layout_check=box_not_found` when the printed box was not found (wrong exam folder?), and `ink_outside_box=yes` when the student also wrote outside the box (below it or in the margins; found by comparing the scan with the blank exam PDF), with a crop of the box and its surroundings in `open_responses/context/`. |
| `<roster>_with_marks.csv` | The class list with the mark column filled. |

## Open answers from the crops: `pevaluate exam-open`

```bash
pevaluate exam-open --index-csv correction/open_responses_index.csv --exam-dir exam_pexams_output \
    --output-dir correction/open --api-key-env ANTHROPIC_API_KEY [--mc-correction-dir correction]
```

- One call per answer: the crop, the question, the expected answer and the rubric. The model transcribes the answer, scores it and writes one short feedback sentence in the student's language. Answers with `ink_outside_box=yes` are graded from the context crop with the box outlined, so text written outside the box counts.
- **Feedback rules** (in the prompt; apply them too when you edit feedback by hand): it reads as written by the teacher, with no trace of automatic grading (no "image", "scan", "box", "transcription", "legible", "reviewed by hand"); a blank answer (or only stray marks) gets score 0 and **no feedback**. Markdown and `$math$` in feedback are rendered in the PDFs.
- `--mc-correction-dir`: for mixed exams; adds the multiple-choice part to the reports and to `overall_marks.csv`.
- `--void-questions`, `--void-questions-nicely`: open questions by number or id; a nicely voided question counts for a student only if it raises their mark (test included). Reuses the grades (no calls).
- `--lang es` (or `ca`, `en`): language of the per-student PDFs. Use the students' language.
- `--regrade-outside-box`: regrades only the answers with writing outside the box that were graded from the box alone (e.g. graded before pexams detected it); everything else, teacher edits included, is kept.
- `--max-image-width 900` (default) keeps handwriting legible at lower cost. `--dry-run` writes prompts without calling.

Outputs: `open_evaluations.yaml` (the file to edit: `score`, `feedback` per answer; the `grader` block keeps the model's original), `open_scores.csv` (with `graded_from` box/context and `teacher_edited`), `needs_review.csv` (answers to look at, with the reason: not graded, crop off the box, writing outside the box not seen, low confidence, warnings about blank/cut/illegible text; teacher-edited answers are left out), `overall_marks.csv` (multiple choice with its counts, each open question `q_<n>`, voided questions, mark /10), `open_responses_report.html/pdf` (all answers with crops), `student_feedback_pdfs/` (one PDF per student, with the image each answer was graded from).

## Blank-paper exams: `pevaluate exam-free`

```bash
pevaluate exam-free --input-path scans.pdf --exam-dir exam_pexams_output --output-dir free --pages-per-exam 2 \
    --api-key-env ANTHROPIC_API_KEY
```

One call per exam with all its pages: reads name and ID, matches answers to questions by content (students number them freely), grades. `--pages-per-exam` must be constant (split the PDF otherwise). Raw responses are cached in `raw_responses/`; same outputs and editing as `exam-open`.

## Submissions (notebooks, reports): `pevaluate <folder>`

Put the LMS download (e.g. the Moodle "download all submissions" zip) in a folder with a rubric and an example of the feedback wanted:

```bash
pevaluate lab1 --rubric rubric.txt --example example.txt --no-reference \
    --files-regex ".*\.(ipynb|html)$" --api-key-env ANTHROPIC_API_KEY
```

- Unzips into `lab1/students/` (with `_submissions_index.json` mapping files to submissions; a notebook and its HTML export count as one submission), and writes `lab1/feedback/feedback_<student>.yaml` (`students`, `feedback`, `mark`, `grader`).
- The rubric lists sections with points summing to 10 and what to say when something is missing. Grading on completeness (code run, outputs present) is cheaper and more robust than grading correctness; the exam checks understanding.
- Notebooks are compacted before sending (plain text instead of HTML tables, repeated lines collapsed, long outputs cut): `--markdown-config '{"max_output_chars": 6000}'` changes the limit.
- `--reference solution.ipynb` adds the teacher's solution to the prompt.

## Combining and publishing

- `pevaluate combine-marks --lab-feedback lab1/feedback --exam-scores correction/open/open_scores.csv --output marks.csv --lab-weight 0.3 --exam-weight 0.7 --roster gradebook.xlsx --roster-output gradebook_filled.xlsx [--notice "..."] [--lang es]`: one row per student with both marks, the weighted final mark and a feedback text; students matched by ID digits, then name. Check `lab_conflict` (two submissions: the higher mark is kept) and the unmatched list.
- **Moodle accepts only two uploads per assignment** (Submissions → Actions): the **grading worksheet CSV** (marks and feedback comments) and a **feedback files zip** (attachments, no marks). A filled Excel gradebook cannot be uploaded to an assignment. So, for each assignment, ask the teacher to *Download grading worksheet* and fill it:
  - from `combine-marks` output: `pevaluate moodle-csv worksheet.csv --marks marks.csv --output filled.csv --partial --feedback-format html`. Each worksheet lists the whole course; a student is filled only where they or their lab partner submitted (status column), so sessions split into several assignments (one per lab group) get each mark once. Students with no lab submission are listed: ask which assignment carries their mark and add `--include-no-lab` there.
  - from lab feedback only: `pevaluate moodle-csv worksheet.csv --feedback-dir lab1/feedback --output filled.csv --partial --feedback-format html`.
  - Check the counts printed (filled, elsewhere, unmatched) add up to the class before handing the files over.
- `pexams moodle-feedback-zip`: one corrected-scan PDF per student, zipped for Moodle's "upload multiple feedback files".

### Moodle: where the teacher clicks

Tell the teacher, with these pictures if useful:
- **Assignment settings → Feedback types:** enable *Feedback comments*, *Offline grading worksheet* and *Feedback files*. Without them there is no worksheet and no feedback upload.
  ![Feedback types](https://raw.githubusercontent.com/OscarPellicer/pevaluate/refs/heads/main/media/moodle.png)
- **Submissions → Actions:**
  - *Download all submissions*, with "Download submissions in folders" ticked: the zip for `pevaluate <folder>`.
  - *Download grading worksheet*: the CSV for `pevaluate moodle-csv`; afterwards *Upload grading worksheet*, ticking *Allow updating records that have been modified more recently in Moodle than in the spreadsheet* (otherwise the rows of students who submitted are skipped).
  - *Upload feedback files in a zip*: the zip from `pexams moodle-feedback-zip`.
  ![Submissions → Actions](https://raw.githubusercontent.com/OscarPellicer/pevaluate/refs/heads/main/media/moodle_submissions_actions.png)
- **Gradebook** (course grades → export to Excel): the roster for `combine-marks`; import the filled copy back through the gradebook import.

### PoliformaT (UPV, Sakai): one zip with grades, comments and PDFs

A PoliformaT assignment (*Tarea*) takes grades, comments and attachments in one zip (*Subir todo*), with the structure of its *Descargar todo* download, which is used as the template:

```bash
pevaluate poliformat-zip "Tarea_20260101120000.zip" --marks correction/open/overall_marks.csv \
    --feedback-pdfs correction/open/student_feedback_pdfs --output "Tarea_subir.zip" --lang es
```

- The download has `<assignment>/grades.xls` (or `.csv`: `Identificador, ID, Apellido, Nombre, Calificación, ...`) and one folder per student, `Apellido, Nombre(ID)` (no accents), with `comments.txt` (the teacher's comment), `feedbackText.html`, `..._submissionText.html`, `Adjuntos al comentario/` (feedback attachments) and `Adjuntos de la entrega/`. It is also the class list: use it to identify the exams (the ID is usually the DNI without letter).
- Grades: two decimals with a decimal comma (`--decimal-sep`). Comment: "Nota: X sobre 10. La corrección de cada pregunta está en el PDF adjunto." (`--lang`, or `--comment "... {mark} ..."`); the PDF `student_feedback_pdfs/<student_id>.pdf` goes to `Adjuntos al comentario/`.
- Students are matched by ID (the ID read from the exam contains the PoliformaT one), then by name. Show the teacher the printed table, especially matches by name, students left ungraded (absent?) and marks without a student. Keep the zip under 200 MB.
- The PDFs carry the name read from the exam (it may be cut or end in `?`). With the download in hand, offer to put the PoliformaT names in `student_name` of `correction_results.csv` (keep `ocr_student_name`), then rerun `correct pexams --only-analysis` (it copies ids and names into `open_responses_index.csv`), `exam-open` (cached, no LLM calls) and `poliformat-zip`.
- **Submissions in PoliformaT** (reports, SQL, notebooks; often by groups, with one member submitting): extract the *Descargar todo* zip and pass it as `--students-dir` with `--no-unzip --whole-submission --prefer-extensions ''` (all the files of a submission in one prompt; only `Adjuntos de la entrega/` and a non-empty submission text count), and `--include-images --pdf-pages-as-images` for reports with diagrams. Before grading, look at what each folder holds: files uploaded to the wrong assignment, the same group submitting twice (grade once), zips. Then `poliformat-zip --feedback-dir <session>/feedback`: the mark and feedback go to the submitter and every member named by the grader; check that every student of each group got a mark.

Tell the teacher, with these pictures if useful:
- In the assignment (*Ver envíos*, "Usar el nuevo calificador" ticked): **Descargar todo**, and later **Subir todo**.
  ![Descargar todo | Subir todo](https://raw.githubusercontent.com/OscarPellicer/pevaluate/refs/heads/main/media/poliformat_enlaces.png)
- **Descargar todo**: tick *Todas*, the grades file (either format) and *Incluir estudiantes que no han realizado un envío todavía* (paper exams have no submissions). Send you the zip.
  ![Descargar todo](https://raw.githubusercontent.com/OscarPellicer/pevaluate/refs/heads/main/media/poliformat_descargar_todo.png)
- **Subir todo**: the zip you built; *Todas*; the **same grades format as the download**; **No publicar información subida** first. They check two or three students in the grader (grade, comment, PDF) and then click *Publicar calificaciones*. The site language must be the one the download was made in.
  ![Subir todo](https://raw.githubusercontent.com/OscarPellicer/pevaluate/refs/heads/main/media/poliformat_subir_todo.png)

## Editing and rerunning

| To change | Edit | Then |
|---|---|---|
| ID or answer read from a scan | `correction_results.csv` | rerun `correct pexams` with `--only-analysis` (redraws the sheets), then `exam-open` to update the overall marks and PDFs |
| A multiple-choice question | — | `--void-questions[-nicely]` + `--only-analysis` |
| An open answer's grade | `score`, `feedback` in `open_evaluations.yaml` | rerun `exam-open`/`exam-free` (same args, no `--force-regrade`) |
| An open question | — | `exam-open --void-questions[-nicely]` |
| A submission's grade | `mark`, `feedback` in its feedback YAML | rerun `combine-marks` / `moodle-csv` |

Before publishing, go through `needs_review.csv` and the `multiple_marks` column with the teacher: show each crop (and the context crop, or the scan page when text may continue outside it) next to the grade.

Never edit a `grader` block. Afterwards: `ptestgen course edits --write` and `ptestgen course metrics --write`.
