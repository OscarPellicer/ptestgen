'''
Read the test sheets, and output first any warnings (if any), and then a csv code block with the following columns: num_matricula, Nombre, Apellidos, Modelo (the number in position X from the code 2505270000X), q1_a (True / False), q1_b (True/False), ..., q30_d (True/False); and as many rows as test sheets (57). Note that a cross means True, whereas: completely black = completely white = False.
Try your best to identify all the requested fields, but most importantly, make sure that the test markings are correctly read. Please throw a warning if unsure about a test marking from a given student:
'''

import argparse
import pandas as pd
import logging
import os
import sys
from collections import OrderedDict
import pyreadr


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_solutions(solutions_rds_path: str) -> dict:
    """
    Reads the R solutions .rds file and structures it for easy access.

    Args:
        solutions_rds_path: Path to the .rds file containing exam solutions.

    Returns:
        A dictionary where keys are model numbers (int, 1-based) and
        values are lists of question metadata. Each question_meta is a dict:
        {'solution': [bool], 'type': str, 'points': float, 'name': str}
    """
    if not os.path.exists(solutions_rds_path):
        logging.error(f"Solutions RDS file not found: {solutions_rds_path}")
        raise FileNotFoundError(f"Solutions RDS file not found: {solutions_rds_path}")

    try:
        rds_data = pyreadr.read_r(solutions_rds_path)
    except Exception as e:
        logging.error(f"Error reading RDS file {solutions_rds_path} with pyreadr: {e}")
        raise

    if not rds_data:
        logging.error(f"No data found in RDS file: {solutions_rds_path}")
        raise ValueError(f"No data found in RDS file: {solutions_rds_path}")

    # exams2nops typically saves a list of exams, often under an unnamed key in the OrderedDict
    main_key = list(rds_data.keys())[0]
    list_of_exam_models = rds_data[main_key]

    if not isinstance(list_of_exam_models, list):
        logging.error(f"Expected a list of exam models in the RDS file, but got type: {type(list_of_exam_models)}")
        raise ValueError("RDS file does not contain a list of exam models as expected.")

    parsed_solutions = {}
    for model_idx, exam_model_data in enumerate(list_of_exam_models):
        model_num = model_idx + 1  # 1-based model number
        questions_meta = []
        if not isinstance(exam_model_data, list):
            logging.warning(f"Model {model_num} data is not a list, but {type(exam_model_data)}. Skipping this model.")
            continue

        for q_data in exam_model_data:
            if not isinstance(q_data, OrderedDict) or 'metainfo' not in q_data:
                logging.warning(f"Skipping invalid question data in model {model_num}: {q_data}")
                continue
            
            metainfo = q_data['metainfo']
            if not isinstance(metainfo, OrderedDict):
                logging.warning(f"Skipping question with invalid metainfo in model {model_num}: {metainfo}")
                continue

            try:
                solution = list(metainfo.get('solution', []))
                q_type = str(metainfo.get('type', 'unknown'))
                points = float(metainfo.get('points', 0.0))
                name = str(metainfo.get('name', f'q_unnamed_{len(questions_meta)+1}'))

                if not all(isinstance(s, (bool, np.bool_)) for s in solution): # np.bool_ for numpy bools
                    logging.warning(f"Question '{name}' in model {model_num} has non-boolean values in solution vector. Attempting conversion.")
                    solution = [bool(s) for s in solution]


                questions_meta.append({
                    'solution': solution,
                    'type': q_type,
                    'points': points,
                    'name': name
                })
            except Exception as e:
                logging.warning(f"Error processing question metainfo in model {model_num} for question named '{metainfo.get('name', 'N/A')}': {e}. Metainfo: {metainfo}")
                continue
        
        if questions_meta: # Only add if we successfully parsed questions
            parsed_solutions[model_num] = questions_meta
            logging.info(f"Parsed model {model_num} with {len(questions_meta)} questions.")
        else:
            logging.warning(f"No questions successfully parsed for model {model_num}.")


    if not parsed_solutions:
        logging.error("No models were successfully parsed from the solutions RDS file.")
        raise ValueError("Failed to parse any models from the solutions RDS file.")
        
    return parsed_solutions


def run_manual_correction(args):
    """
    Main logic for correcting exams based on manual CSV and solutions RDS.
    """
    if not os.path.exists(args.corrected_answers_csv):
        logging.error(f"Corrected answers CSV file not found: {args.corrected_answers_csv}")
        return False

    try:
        answers_df = pd.read_csv(args.corrected_answers_csv)
        logging.info(f"Loaded {len(answers_df)} student answers from {args.corrected_answers_csv}")
    except Exception as e:
        logging.error(f"Error reading corrected answers CSV {args.corrected_answers_csv}: {e}")
        return False

    try:
        parsed_solutions = parse_solutions(args.solutions_rds)
    except Exception as e:
        logging.error(f"Failed to parse solutions RDS file: {e}")
        return False

    results_data = []
    
    # Determine number of questions and options from CSV structure (e.g., q1_a to q30_d)
    # This assumes a fixed structure like pln_2025_gem.csv
    num_questions = 0
    question_cols = [col for col in answers_df.columns if col.startswith('q') and '_' in col]
    if question_cols:
        num_questions = max([int(col.split('_')[0][1:]) for col in question_cols])
    
    if num_questions == 0:
        logging.error("Could not determine the number of questions from the CSV column names (e.g., q1_a, q2_b).")
        return False
    logging.info(f"Determined {num_questions} questions from CSV structure.")

    # Assuming 4 options ('a', 'b', 'c', 'd') based on pln_2025_gem.csv.
    # This should match the length of solution vectors in RDS.
    options_chars = ['a', 'b', 'c', 'd'] 
    num_options_per_q = len(options_chars)

    for index, row in answers_df.iterrows():
        student_id = row.get('num_matricula', f"student_{index}")
        student_name = row.get('Nombre', '')
        student_surname = row.get('Apellidos', '')
        model_num = int(row['Modelo'])

        if model_num not in parsed_solutions:
            logging.warning(f"Model {model_num} for student {student_id} not found in parsed solutions. Skipping student.")
            continue
        
        solutions_for_model = parsed_solutions[model_num]

        if len(solutions_for_model) != num_questions:
            logging.warning(f"Mismatch in question count for model {model_num}. Expected {num_questions} from CSV, found {len(solutions_for_model)} in RDS for student {student_id}. Skipping student.")
            continue

        student_total_points = 0.0
        student_q_details = {} # For detailed CSV output if needed later

        for q_idx in range(num_questions): # 0 to num_questions-1
            q_num_csv = q_idx + 1 # 1-based for CSV columns like 'q1_a'
            question_meta = solutions_for_model[q_idx]

            student_answer_options_bool = []
            try:
                for opt_char_idx, opt_char in enumerate(options_chars):
                    col_name = f'q{q_num_csv}_{opt_char}'
                    # Ensure the value from CSV is correctly interpreted as boolean
                    csv_val = row[col_name]
                    if isinstance(csv_val, str):
                        student_answer_options_bool.append(csv_val.lower() == 'true')
                    else:
                        student_answer_options_bool.append(bool(csv_val))
            except KeyError as e:
                logging.error(f"Missing column {e} for student {student_id}, question {q_num_csv}. Assuming all False for this question.")
                student_answer_options_bool = [False] * num_options_per_q


            q_type = question_meta['type']
            correct_solution_vector = question_meta['solution']
            q_max_points = question_meta['points']
            
            if len(correct_solution_vector) != num_options_per_q:
                logging.warning(f"Solution vector length mismatch for Q{q_num_csv} in Model {model_num} "
                                f"(expected {num_options_per_q}, got {len(correct_solution_vector)}). Skipping question for student {student_id}.")
                student_q_details[f'q{q_num_csv}_points'] = 0.0
                continue


            current_q_points = 0.0

            if q_type == 'schoice':
                answered_indices = [i for i, x in enumerate(student_answer_options_bool) if x]
                
                # Ensure there's exactly one True in the correct solution for schoice
                if sum(correct_solution_vector) != 1:
                    logging.warning(f"Schoice question {question_meta['name']} (Q{q_num_csv}) in Model {model_num} does not have exactly one correct answer in solution. Skipping.")
                    student_q_details[f'q{q_num_csv}_points'] = 0.0
                    continue
                correct_index = correct_solution_vector.index(True)

                if not answered_indices: # No answer
                    current_q_points = 0.0
                elif len(answered_indices) > 1: # Multiple answers for schoice
                    if args.partial_eval:
                        current_q_points = args.negative_points * q_max_points
                    else:
                        current_q_points = 0.0
                else: # Single answer
                    student_choice_idx = answered_indices[0]
                    if student_choice_idx == correct_index:
                        current_q_points = q_max_points
                    else: # Incorrect answer
                        if args.partial_eval:
                            current_q_points = args.negative_points * q_max_points
                        else:
                            current_q_points = 0.0
            
            elif q_type == 'mchoice':
                selected_correct_count = 0
                n_actual_correct_options = sum(correct_solution_vector)
                selected_incorrect_count = 0

                for i in range(num_options_per_q):
                    if student_answer_options_bool[i]: # If student selected this option
                        if correct_solution_vector[i]: # And it's a correct option
                            selected_correct_count += 1
                        else: # And it's an incorrect option
                            selected_incorrect_count +=1
                
                is_perfect_match = (selected_correct_count == n_actual_correct_options and selected_incorrect_count == 0)
                
                if is_perfect_match:
                    current_q_points = q_max_points
                else: # Not a perfect match
                    if args.partial_eval: # Python's --partial-eval flag
                        current_q_points = args.negative_points * q_max_points
                    else: # if --no-partial-eval
                        current_q_points = 0.0
            else:
                logging.warning(f"Unknown question type '{q_type}' for Q{q_num_csv} Model {model_num}. Scoring as 0.")
            
            student_total_points += current_q_points
            student_q_details[f'q{q_num_csv}_points'] = round(current_q_points, 3)

        student_summary = {
            'num_matricula': student_id,
            'Nombre': student_name,
            'Apellidos': student_surname,
            'Modelo': model_num,
            'total_points': round(student_total_points, 3)
        }
        # student_summary.update(student_q_details) # Optionally add per-question points
        results_data.append(student_summary)

    if not results_data:
        logging.warning("No student results were processed.")
        return False

    results_df = pd.DataFrame(results_data)

    # Calculate max possible score for scaling if not provided or invalid
    max_possible_score = args.max_score
    if max_possible_score is None or max_possible_score <= 0:
        logging.info("--max-score not provided or invalid. Calculating from solutions for first available model.")
        first_model_key = list(parsed_solutions.keys())[0]
        first_model_solutions = parsed_solutions[first_model_key]
        calculated_max_score = sum(q['points'] for q in first_model_solutions if q['points'] > 0) # Sum positive points
        if calculated_max_score > 0 :
            max_possible_score = calculated_max_score
            logging.info(f"Calculated max possible score: {max_possible_score}")
        else:
            logging.warning("Could not calculate a valid max_score from solutions. Scaling will not be effective if max_score is not positive.")
            max_possible_score = 0 # Avoid division by zero if user didn't provide one

    if max_possible_score and max_possible_score > 0:
        results_df['scaled_mark'] = round(results_df['total_points'] * args.scale_mark_to / max_possible_score, 2)
        # Ensure scaled mark is not negative if total_points can be negative
        results_df['scaled_mark'] = results_df['scaled_mark'].apply(lambda x: max(0, x))
    else:
        logging.warning("Max score is 0 or not available, cannot scale marks. 'scaled_mark' will be 0 or absent.")
        results_df['scaled_mark'] = 0.0 if 'total_points' in results_df.columns else pd.NA


    os.makedirs(args.output_path, exist_ok=True)
    output_csv_path = os.path.join(args.output_path, "exam_corrected_results_manual.csv")
    
    try:
        results_df.to_csv(output_csv_path, index=False, sep=';', encoding='utf-8-sig')
        logging.info(f"Correction results saved to: {output_csv_path}")
    except Exception as e:
        logging.error(f"Error saving results CSV to {output_csv_path}: {e}")
        return False
        
    return True

def main():
    parser = argparse.ArgumentParser(description="Python script for correcting exams from a manual CSV and solutions.rds.")
    
    parser.add_argument("--corrected-answers-csv", type=str, required=True,
                        help="Path to the CSV file containing manually corrected student answers (e.g., pln_2025_gem.csv).")
    parser.add_argument("--solutions-rds", type=str, required=True,
                        help="Path to the .rds file containing exam solutions (generated by R/exams).")
    parser.add_argument("--output-path", type=str, required=True,
                        help="Directory to save the output results CSV.")
    
    parser.add_argument("--partial-eval", action=argparse.BooleanOptionalAction, default=True,
                        help="Enable partial scoring (penalties for incorrect answers). If --no-partial-eval, incorrect answers get 0 points. (default: enabled)")
    parser.add_argument("--negative-points", type=float, default=-1/3,
                        help="Fractional penalty for incorrect answers when partial eval is enabled (e.g., -0.3333 for -1/3 of question's points). (default: %(default)f)")
    parser.add_argument("--max-score", type=float, default=None,
                        help="Maximum raw score of the exam (e.g., 30 if 30 questions of 1 point). Used for scaling. If not provided, will be calculated from solutions.")
    parser.add_argument("--scale-mark-to", type=float, default=10.0,
                        help="Target score for scaling the final mark (e.g., 10). (default: %(default)f)")

    args = parser.parse_args()

    # Import numpy here for the parse_solutions bool check, only if needed
    global np 
    import numpy as np


    if run_manual_correction(args):
        logging.info("Exam correction process completed successfully.")
        sys.exit(0)
    else:
        logging.error("Exam correction process failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
