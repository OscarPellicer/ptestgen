import os
import csv
import json
import logging
import random
import re
import string
from typing import List, Dict, Optional

from Levenshtein import distance

from .schemas import QuestionRecord, QuestionStageContent, QuestionContent, ChangeMetrics, EvaluationData

METADATA_FILENAME = "metadata.tsv"
QUESTIONS_FILENAME = "questions.md"

METADATA_COLUMNS = [
    "question_id", "source_material", "image_reference",
    # Generated Stage
    "generated_text", "generated_answers_json",
    "generated_eval_difficulty", "generated_eval_pedagogy", "generated_eval_clarity", "generated_eval_distractors", "generated_eval_comments", "generated_eval_guessed_correctly",
    # Reviewed Stage
    "reviewed_text", "reviewed_answers_json",
    "reviewed_eval_difficulty", "reviewed_eval_pedagogy", "reviewed_eval_clarity", "reviewed_eval_distractors", "reviewed_eval_comments", "reviewed_eval_guessed_correctly",
    # Final Stage
    "final_text", "final_answers_json",
    # Changes Gen -> Rev
    "changes_gen_rev_status", "changes_gen_rev_lev_question", "changes_gen_rev_lev_answers", "changes_gen_rev_rel_lev_question", "changes_gen_rev_rel_lev_answers",
    # Changes Rev -> Man
    "changes_rev_man_status", "changes_rev_man_lev_question", "changes_rev_man_lev_answers", "changes_rev_man_rel_lev_question", "changes_rev_man_rel_lev_answers",
]

def generate_question_id(input_material_path: Optional[str] = None) -> str:
    """Generates a unique ID for a question."""
    random_id = ''.join(random.choices(string.digits, k=8))
    if input_material_path:
        # Use the basename of the source material, remove extension
        base_name = os.path.splitext(os.path.basename(input_material_path))[0]
        # Replace spaces with underscores
        name_with_underscores = base_name.replace(' ', '_')
        # Sanitize basename for use in an ID (remove anything not alphanumeric, _, or -)
        sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '', name_with_underscores)
        return f"{sanitized_name}_{random_id}"
    else:
        return f"custom_{random_id}"

def _escape_tsv_field(text: str) -> str:
    """Replaces tabs and newlines to prevent corrupting TSV format."""
    if text is None:
        return ""
    return str(text).replace('\t', '    ').replace('\n', '\\n').replace('\r', '')

def _serialize_record(record: QuestionRecord) -> Dict[str, str]:
    """Serializes a QuestionRecord object into a dictionary for TSV writing."""
    row = {col: "" for col in METADATA_COLUMNS}

    row["question_id"] = record.question_id
    row["source_material"] = _escape_tsv_field(record.source_material)
    row["image_reference"] = _escape_tsv_field(record.image_reference)

    # --- Generated Stage ---
    if record.generated:
        content = record.generated.content
        row["generated_text"] = _escape_tsv_field(content.text)
        answers = {
            "correct": content.correct_answer,
            "distractors": content.distractors,
            "explanation": content.explanation or ""
        }
        row["generated_answers_json"] = json.dumps(answers, ensure_ascii=False)
        if record.generated.evaluation:
            eval_data = record.generated.evaluation
            row["generated_eval_difficulty"] = str(eval_data.difficulty_score or "")
            row["generated_eval_pedagogy"] = str(eval_data.pedagogical_value or "")
            row["generated_eval_clarity"] = str(eval_data.clarity_score or "")
            row["generated_eval_distractors"] = str(eval_data.distractor_plausibility_score or "")
            row["generated_eval_comments"] = _escape_tsv_field(eval_data.evaluation_comments)
            row["generated_eval_guessed_correctly"] = str(eval_data.evaluator_guessed_correctly or "")

    # --- Reviewed Stage ---
    if record.reviewed:
        content = record.reviewed.content
        row["reviewed_text"] = _escape_tsv_field(content.text)
        answers = {
            "correct": content.correct_answer,
            "distractors": content.distractors,
            "explanation": content.explanation or ""
        }
        row["reviewed_answers_json"] = json.dumps(answers, ensure_ascii=False)
        if record.reviewed.evaluation:
            eval_data = record.reviewed.evaluation
            row["reviewed_eval_difficulty"] = str(eval_data.difficulty_score or "")
            row["reviewed_eval_pedagogy"] = str(eval_data.pedagogical_value or "")
            row["reviewed_eval_clarity"] = str(eval_data.clarity_score or "")
            row["reviewed_eval_distractors"] = str(eval_data.distractor_plausibility_score or "")
            row["reviewed_eval_comments"] = _escape_tsv_field(eval_data.evaluation_comments)
            row["reviewed_eval_guessed_correctly"] = str(eval_data.evaluator_guessed_correctly or "")

    # --- Final Stage ---
    if record.final:
        content = record.final.content
        row["final_text"] = _escape_tsv_field(content.text)
        answers = {
            "correct": content.correct_answer,
            "distractors": content.distractors,
            "explanation": content.explanation or ""
        }
        row["final_answers_json"] = json.dumps(answers, ensure_ascii=False)
        # Note: final stage doesn't have its own evaluation in this model

    # --- Changes Gen -> Rev ---
    if record.changes_gen_to_rev:
        changes = record.changes_gen_to_rev
        row["changes_gen_rev_status"] = changes.status
        row["changes_gen_rev_lev_question"] = str(changes.levenshtein_question)
        row["changes_gen_rev_lev_answers"] = str(changes.levenshtein_answers)
        row["changes_gen_rev_rel_lev_question"] = f"{changes.rel_levenshtein_question:.4f}"
        row["changes_gen_rev_rel_lev_answers"] = f"{changes.rel_levenshtein_answers:.4f}"

    # --- Changes Rev -> Man ---
    if record.changes_rev_to_man:
        changes = record.changes_rev_to_man
        row["changes_rev_man_status"] = changes.status
        row["changes_rev_man_lev_question"] = str(changes.levenshtein_question)
        row["changes_rev_man_lev_answers"] = str(changes.levenshtein_answers)
        row["changes_rev_man_rel_lev_question"] = f"{changes.rel_levenshtein_question:.4f}"
        row["changes_rev_man_rel_lev_answers"] = f"{changes.rel_levenshtein_answers:.4f}"

    return row

def write_metadata_tsv(records: List[QuestionRecord], output_path: str):
    """Writes a list of QuestionRecord objects to a TSV file."""
    logging.info(f"Writing metadata to {output_path}")
    
    rows = [_serialize_record(rec) for rec in records]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=METADATA_COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)

def write_questions_md(records: List[QuestionRecord], output_path: str):
    """Writes the latest version of questions to a simplified Markdown file."""
    logging.info(f"Writing {len(records)} questions to Markdown file: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Questions for Manual Review\n\n")
        
        for record in records:
            content = record.get_latest_content()
            if content:
                f.write(f"## {record.question_id}\n")
                
                # Add image reference if it exists
                if record.image_reference:
                    # Make path relative to the markdown file for portability
                    md_dir = os.path.dirname(os.path.abspath(output_path))
                    relative_path = os.path.relpath(os.path.abspath(record.image_reference), md_dir)
                    # On Windows, relpath can produce backslashes, which need to be forward slashes for markdown
                    relative_path = relative_path.replace("\\", "/")
                    f.write(f"> ![Image for question]({relative_path})\n\n")

                f.write(f"{content.text}\n\n")
                
                f.write(f"* {content.correct_answer}\n")
                for distractor in content.distractors:
                    f.write(f"* {distractor}\n")
                
                if content.explanation:
                    f.write(f"\n**Explanation:**\n{content.explanation}\n")
                
                f.write("\n\n") # Use two newlines as a separator

def get_artifact_paths(md_path: str) -> (str, str):
    """
    Given a path to a markdown file, returns the paths for both the MD and the corresponding TSV file.
    Example: 'path/to/file.md' -> ('path/to/file.md', 'path/to/file.tsv')
    """
    base = os.path.splitext(md_path)[0]
    return md_path, f"{base}.tsv"

def write_artifacts(records: List[QuestionRecord], md_path: str, tsv_path: str):
    """Orchestrates writing both the simplified markdown and the full metadata TSV."""
    # Create the directory if it doesn't exist
    output_dir = os.path.dirname(md_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    write_questions_md(records, md_path)
    write_metadata_tsv(records, tsv_path)
    logging.info(f"Artifacts successfully written to '{md_path}' and '{tsv_path}'")

def _deserialize_record(row: Dict[str, str]) -> QuestionRecord:
    """Deserializes a dictionary from a TSV row into a QuestionRecord object."""
    
    def _parse_answers(json_str: str) -> Dict:
        if not json_str: return {}
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}

    # A helper to safely create QuestionContent
    def _create_content(text_key, answers_key) -> Optional[QuestionContent]:
        if row.get(text_key):
            answers = _parse_answers(row.get(answers_key, '{}'))
            return QuestionContent(
                text=row[text_key],
                correct_answer=answers.get('correct', ''),
                distractors=answers.get('distractors', []),
                explanation=answers.get('explanation')
            )
        return None

    # A helper to safely create EvaluationData
    def _create_evaluation(prefix) -> Optional[EvaluationData]:
        if row.get(f"{prefix}_eval_difficulty"):
            try:
                return EvaluationData(
                    difficulty_score=float(row[f"{prefix}_eval_difficulty"]),
                    pedagogical_value=float(row[f"{prefix}_eval_pedagogy"]),
                    clarity_score=float(row[f"{prefix}_eval_clarity"]),
                    distractor_plausibility_score=float(row[f"{prefix}_eval_distractors"]),
                    evaluation_comments=row[f"{prefix}_eval_comments"],
                    evaluator_guessed_correctly=row[f"{prefix}_eval_guessed_correctly"].lower() == 'true'
                )
            except (ValueError, TypeError):
                return None
        return None

    record = QuestionRecord(question_id=row['question_id'])
    record.source_material = row.get('source_material')
    record.image_reference = row.get('image_reference')

    gen_content = _create_content('generated_text', 'generated_answers_json')
    if gen_content:
        record.generated = QuestionStageContent(content=gen_content, evaluation=_create_evaluation('generated'))

    rev_content = _create_content('reviewed_text', 'reviewed_answers_json')
    if rev_content:
        record.reviewed = QuestionStageContent(content=rev_content, evaluation=_create_evaluation('reviewed'))
        
    final_content = _create_content('final_text', 'final_answers_json')
    if final_content:
        record.final = QuestionStageContent(content=final_content)

    # --- Deserialize Change Metrics ---
    if row.get("changes_gen_rev_status"):
        try:
            record.changes_gen_to_rev = ChangeMetrics(
                status=row["changes_gen_rev_status"],
                levenshtein_question=int(row["changes_gen_rev_lev_question"]),
                levenshtein_answers=int(row["changes_gen_rev_lev_answers"]),
                rel_levenshtein_question=float(row["changes_gen_rev_rel_lev_question"]),
                rel_levenshtein_answers=float(row["changes_gen_rev_rel_lev_answers"]),
            )
        except (ValueError, KeyError):
            logging.warning(f"Could not parse gen->rev change metrics for {record.question_id}")
    
    if row.get("changes_rev_man_status"):
        try:
            record.changes_rev_to_man = ChangeMetrics(
                status=row["changes_rev_man_status"],
                levenshtein_question=int(row["changes_rev_man_lev_question"]),
                levenshtein_answers=int(row["changes_rev_man_lev_answers"]),
                rel_levenshtein_question=float(row["changes_rev_man_rel_lev_question"]),
                rel_levenshtein_answers=float(row["changes_rev_man_rel_lev_answers"]),
            )
        except (ValueError, KeyError):
            logging.warning(f"Could not parse rev->man change metrics for {record.question_id}")
    
    return record


def read_metadata_tsv(path: str) -> List[QuestionRecord]:
    """Reads a TSV file and returns a list of QuestionRecord objects."""
    if not os.path.exists(path):
        logging.error(f"Metadata file not found: {path}")
        return []
    
    records = []
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            records.append(_deserialize_record(row))
    return records

def read_questions_md(path: str) -> Dict[str, QuestionContent]:
    """Parses a simplified Markdown file into a dictionary of QuestionContent objects."""
    if not os.path.exists(path):
        logging.error(f"Questions markdown file not found: {path}")
        return {}
        
    questions: Dict[str, QuestionContent] = {}
    
    # Split the content by the new question header '## ' that appears at the start of a line
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    question_blocks = re.split(r'(?=^## )', content, flags=re.MULTILINE)

    for block in question_blocks:
        block = block.strip()
        if not block.startswith("##"):
            continue

        lines = block.split('\n')
        
        # Parse ID from header: "## question_id"
        header_line = lines[0]
        match = re.match(r'^##\s+(.+)', header_line)
        if not match:
            continue
        question_id = match.group(1).strip()
        
        content_lines = lines[1:]
        
        # Check for and extract a quoted image line
        image_path = None
        if content_lines and content_lines[0].strip().startswith('>'):
            img_match = re.search(r'!\[.*\]\((.*)\)', content_lines[0])
            if img_match:
                image_path = img_match.group(1).strip()
                # Remove the image line from the content
                content_lines = content_lines[1:]

        first_answer_idx = -1
        for i, line in enumerate(content_lines):
            if line.strip().startswith(('*', '-', '1.')):
                first_answer_idx = i
                break
        
        if first_answer_idx == -1:
            logging.warning(f"Could not find any answers for question ID '{question_id}'. Skipping.")
            continue
            
        question_text = "\n".join(content_lines[:first_answer_idx]).strip()
        
        answer_and_exp_lines = content_lines[first_answer_idx:]
        
        answers = []
        explanation_lines = []
        is_parsing_exp = False
        
        for line in answer_and_exp_lines:
            stripped = line.strip()
            if stripped.lower().startswith("**explanation:**"):
                is_parsing_exp = True
                continue
            
            if is_parsing_exp:
                explanation_lines.append(line)
                continue
            
            if stripped.startswith(('* ', '- ')):
                answers.append(re.sub(r'^[\*\-]\s*', '', stripped))
            elif stripped.startswith('1. '):
                 answers.append(re.sub(r'^\d+\.\s*', '', stripped))

        if not answers:
            continue

        questions[question_id] = QuestionContent(
            text=question_text,
            correct_answer=answers[0],
            distractors=answers[1:],
            explanation="\n".join(explanation_lines).strip() or None,
            image_reference=image_path
        )
        
    return questions

def calculate_changes(old_stage: QuestionStageContent, new_stage: QuestionStageContent) -> ChangeMetrics:
    """Calculates change metrics between two stages of a question."""
    old_content = old_stage.content
    new_content = new_stage.content
    
    q_dist = distance(old_content.text, new_content.text)
    
    old_answers_str = " ".join([old_content.correct_answer] + old_content.distractors)
    new_answers_str = " ".join([new_content.correct_answer] + new_content.distractors)
    a_dist = distance(old_answers_str, new_answers_str)
    
    status = "modified" if q_dist > 0 or a_dist > 0 else "unchanged"
    
    return ChangeMetrics(
        status=status,
        levenshtein_question=q_dist,
        levenshtein_answers=a_dist,
        rel_levenshtein_question=q_dist / len(old_content.text) if old_content.text else 0,
        rel_levenshtein_answers=a_dist / len(old_answers_str) if old_answers_str else 0,
    )

def synchronize_artifacts(records: List[QuestionRecord], md_questions: Dict[str, QuestionContent]) -> List[QuestionRecord]:
    """
    Synchronizes records from TSV with content from the manually edited Markdown file.
    - Marks records as 'removed' if they are no longer in the MD file.
    - Adds new records for questions found in the MD but not in the TSV.
    - Updates records where the content has been modified.
    """
    logging.info("Synchronizing artifacts from TSV and Markdown...")
    
    md_ids = set(md_questions.keys())
    record_ids = {rec.question_id for rec in records}
    
    final_records: List[QuestionRecord] = []
    
    # Process existing records
    for record in records:
        if record.question_id not in md_ids:
            # Question was deleted
            logging.info(f"Question '{record.question_id}' removed during manual review.")
            if record.reviewed:
                record.changes_rev_to_man = ChangeMetrics(status="removed")
            elif record.generated: # Should have at least a generated stage
                 record.changes_gen_to_rev = ChangeMetrics(status="removed") # Or a new change status?
            final_records.append(record)
        else:
            # Question exists, check for modifications
            manual_content = md_questions[record.question_id]
            latest_content = record.get_latest_content()

            
            record.final = QuestionStageContent(content=manual_content)

            if manual_content != latest_content:
                logging.info(f"Question '{record.question_id}' modified during manual review.")
                if record.reviewed:
                    record.changes_rev_to_man = calculate_changes(record.reviewed, record.final)
                elif record.generated:
                    # This case implies no review stage was run
                    # For now, let's compare manual vs generated
                    # We might need a new ChangeMetrics field for this
                    pass
            else:
                # Still calculate changes to mark as "unchanged" if necessary
                if record.reviewed:
                    record.changes_rev_to_man = calculate_changes(record.reviewed, record.final)


            final_records.append(record)

    # Add new questions that were manually added to the markdown
    new_ids = md_ids - record_ids
    for new_id in new_ids:
        logging.info(f"New question '{new_id}' added during manual review.")
        manual_content = md_questions[new_id]
        new_record = QuestionRecord(
            question_id=new_id,
            source_material="manual_addition",
            final=QuestionStageContent(content=manual_content),
            # Mark previous stages as "non-existent" or similar
            changes_rev_to_man=ChangeMetrics(status="added")
        )
        final_records.append(new_record)
        
    logging.info(f"Synchronization complete. Final record count: {len(final_records)}")
    return final_records
