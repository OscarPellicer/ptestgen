# Exam PDFs: `ptestgen export pexams`

Run in the folder of the questions file (paths are relative to it):

```bash
ptestgen export pexams exam.md --exam-title "Midterm" --exam-course "Course" --exam-date 2026-11-05 \
    --num-models 2 --total-students 30 --extra-model-templates 2 --lang es \
    --custom-header header.md --fill-answer-space
```

| Option | What to ask / choose |
|---|---|
| `--num-models N` | Versions with shuffled questions and options (default 1). 2-4 against copying; 1 for open-answer-only exams. |
| `--total-students N` | Writes `all_exams.pdf` with N exams (models alternated) to print in one go. |
| `--extra-model-templates N` | Spare answer sheets per model, appended to `all_exams.pdf` (multiple choice only). |
| `--lang es\|en\|ca…` | Language of the printed labels (name, ID, signature, instructions of the answer sheet). Always pass it. |
| `--exam-title`, `--exam-course`, `--exam-date` | Printed on every model. |
| `--custom-header file.md` | Instructions before the questions: duration, penalty, allowed material, language of the answers. |
| `--columns 1\|2\|3`, `--font-size 9pt` | Layout; 2 columns suit long multiple-choice tests. |
| `--mc-total-points X` | Splits X points evenly among the multiple-choice questions (open questions keep their `points`). |
| `--show-points auto\|always\|never` | Prints `[1.5 pt]` after each number (auto: when values differ or there are open questions). |
| `--fill-answer-space` | Grows the open-answer boxes to use the free space at the bottom of each page. |
| `--shuffle-questions`, `--shuffle-answers` | Shuffle seeds. |
| `--generate-fakes N`, `--generate-references` | Simulated scans (random answers / correct answers) to test the correction before the exam. |

## Outputs (`<questions>_pexams_output/`)

- `exam_model_N.pdf`: each model; `all_exams.pdf` with `--total-students`.
- `exam_model_N_questions.json`: questions, order and solutions per model (needed to correct; keep it).
- `open_answer_areas.json`: position of every open-answer box (used to crop the scans).
- `simulated_scans/`, `reference_scans/` when requested.
- Next to the `.md`: `<questions>.tsv`, the history of each question (generated, reviewed, statistics after correction). `export` creates it from the `.md` when missing.

## Checking the PDF

Render every page to PNG (PyMuPDF: `fitz.open(pdf)[i].get_pixmap(dpi=80).save(...)`) and look at it:
- the page count is what the teacher expects (1 sheet double-sided?);
- no question or box is cut by a page break, open-answer boxes are large enough for the expected answer;
- images, code and formulas render (MathJax loads from a CDN: a formula left as `$...$` means it failed; rebuild);
- with no multiple-choice questions there is no answer sheet: the header (model, ID, name, signature) is printed on the first page.

Box positions: `python -c "import json;[print(a['question_id'],a['page_index'],round(a['y_mm']+a['height_mm'])) for a in json.load(open('open_answer_areas.json'))]"` (bottom at most ~253 mm on A4).

## Once printed

The scans can only be read with the exact `exam_model_N_questions.json` and `open_answer_areas.json` that produced the printed PDF. Do not export again into the same folder (`locked: true` in the course record). To change an exam after printing, export into a new folder and keep the printed one.
