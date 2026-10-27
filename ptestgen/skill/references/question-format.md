# Question format (Markdown)

One file per exam. `ptestgen` and `pexams` read it with the same parser. Each question is a `## <id> {attributes}` block; ids must be unique and stable (statistics and grades are keyed by them).

## Multiple choice

```markdown
## q_hl7v2 {points=1}
A plain-text file with segments like `PID|...|GARCIA^JUAN|...` follows the standard:
* HL7 v2
* HL7 v3
* FHIR
* CDA

**Explanation:**
HL7 v2 uses pipe-delimited text segments; v3 and CDA are XML; FHIR is JSON/XML resources.
```

- The **first option is the correct one**; options are shuffled in every model.
- The first line starting with `* `, `- ` or `1. ` starts the options, so the question text cannot contain a list.
- Options are one line each (inline code and math only).
- `**Explanation:**` is not printed; it explains the answer in reports and feedback.

## Open answer

```markdown
## p1_threshold {type=open_answer points=1 lines=6}
With the lab's utility matrix the optimal threshold is 0.28 instead of 0.5. What is a false negative here? Why is the threshold lower than 0.5? / *English version in italics for bilingual exams.*

**Expected answer:**
A false negative is a patient who dies but was predicted to survive; it costs more than a false positive, so ...

**Rubric:**
- 50 %: false negative defined in the clinical context.
- 50 %: cost asymmetry explains the lower threshold.
```

- `lines` sets the box height (7 mm per line, fractions allowed); `--fill-answer-space` grows boxes into the free space of their page. `show_lines=true` prints guide lines; `height_mm=` fixes the height.
- `**Expected answer:**` and `**Rubric:**` are not printed: they are what the LLM grades against. Make the rubric concrete (percentages per element, what is enough), and give the numbers the student needs in the statement.
- A question answerable in 2-4 lines takes about 3 minutes; a 10-minute quiz fits 3.

## Header attributes

| Attribute | Meaning |
|---|---|
| `type=open_answer` (or `open`) | Open question (default: multiple choice). |
| `points=1.5` | Value; printed as `[1.5 pt]` when values differ or there are open questions (`--show-points`). |
| `lines=8.5`, `height_mm=60`, `show_lines=true` | Open-answer box. |
| `font_size=8pt` | Per-question font size. |

## Text features (question text, options, custom header)

| Feature | Syntax |
|---|---|
| Emphasis | `*italic*`, `_italic_`, `**bold**` (underscores inside words stay literal) |
| Line breaks | a newline is a line break; a blank line a new paragraph |
| Code | `` `inline` `` anywhere; fenced blocks (```` ```python ````) in the question text and header only |
| Math | `$x_1$` inline, `$$\sum_i x_i$$` display (may span lines), `\$` literal dollar. MathJax loads from a CDN: check the PDF |
| Images | `![alt](fig.png)` anywhere, several per question, paths relative to the `.md` |
| Image layout | in the alt text: `![w:60mm right\|ECG lead II](ecg.png)`: `w:`/`h:` in px, mm, cm or % (plain number = px); `left`/`right` (text wraps) or `center`; after `\|` the alt text (not printed) |
| Old image line | `> ![alt](img.png)` right after the header still works: it becomes an ordinary image below the text (at the start, if its alt has a layout spec) |
| Comments | `<!-- ... -->` are ignored (also a whole commented-out question) |

Open-answer boxes always start below floated images. Moodle XML and GIFT exports render the text like the PDF and embed every image (in the text, options and explanation) with its layout; R/exams takes the images of the question text (placed below it); Wooclap has no images (questions with one are skipped).

## Bilingual exams

Write each statement once per language in the same paragraph, `castellano / *English*`, and tell students in the header that they may answer in either; the grader answers in the student's language.

## Editing after review

The teacher may edit the `.md` directly: wording, options, points, rubric. On the next `export`, ptestgen records the manual changes in the `.tsv` (stage "manual review"). Changing a question after the exam was printed does not change the printed PDF; changes to `Expected answer`/`Rubric` do affect grading (pevaluate reads them from `exam_model_N_questions.json`, so re-export into a **new** folder, or edit the JSON, and say so in the course record).
