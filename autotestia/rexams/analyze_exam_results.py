import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os
import numpy as np
from collections import Counter
import unidecode # For improved alphabetical sorting
import logging
from typing import Optional, List # Added Optional, List
from tabulate import tabulate # Added tabulate import

def parse_q_list(q_str: Optional[str]) -> List[int]:
    """Converts a comma-separated string of question numbers to a sorted list of unique integers."""
    if not q_str:
        return []
    try:
        return sorted(list(set(int(q.strip()) for q in q_str.split(',') if q.strip().isdigit())))
    except ValueError:
        logging.warning(f"Invalid format for question list string: '{q_str}'. Expected comma-separated numbers. Returning empty list.")
        return []

def analyze_results(csv_filepath, max_score, output_dir=".", void_questions_str: Optional[str] = None, void_questions_nicely_str: Optional[str] = None):
    """
    Analyzes exam results from a CSV file, scales scores to 0-10, 
    plots score distribution with 11 specific bars, and shows statistics.
    Allows for voiding questions or voiding them 'nicely' (only if incorrect/unanswered).

    Args:
        csv_filepath (str): Path to the exam results CSV file.
        max_score (float): The maximum possible raw score for the exam (for normalization).
        output_dir (str): Directory to save the output plot.
        void_questions_str (Optional[str]): Comma-separated string of question numbers to void completely.
        void_questions_nicely_str (Optional[str]): Comma-separated string of question numbers to void only if incorrect/NA.
    """
    if not os.path.exists(csv_filepath):
        print(f"Error: CSV file not found at {csv_filepath}")
        return

    try:
        # Get column names first to build dtype mapping
        temp_df_for_cols = pd.read_csv(csv_filepath, sep=';', decimal='.', nrows=0) # Read only header
        all_columns = temp_df_for_cols.columns.tolist()
        
        dtype_spec = {}
        for col_name in all_columns:
            if col_name.startswith('answer.') or col_name.startswith('solution.'):
                dtype_spec[col_name] = str # Force answer and solution columns to be strings

        df = pd.read_csv(csv_filepath, sep=';', decimal='.', dtype=dtype_spec)
        print(f"Successfully loaded {csv_filepath}")
        # print(f"Columns found: {df.columns.tolist()}") # Already have all_columns
        # print(f"Data types:\n{df.dtypes}") # Optional: for debugging types
    except Exception as e:
        print(f"Error reading CSV file {csv_filepath}: {e}")
        return

    if 'points' not in df.columns:
        print(f"Error: 'points' column not found in {csv_filepath}.")
        print("Please ensure the CSV contains a 'points' column with raw scores.")
        return

    # Ensure 'registration' column exists and is string for merging, if it's present
    if 'registration' in df.columns:
        df['registration'] = df['registration'].astype(str)
    else:
        print(f"Warning: 'registration' column not found in {csv_filepath}. Student list with marks cannot be generated.")

    df['points_numeric'] = pd.to_numeric(df['points'], errors='coerce')
    
    original_rows = len(df)
    df.dropna(subset=['points_numeric'], inplace=True)
    if len(df) < original_rows:
        print(f"Warning: Dropped {original_rows - len(df)} rows due to non-numeric 'points' values.")

    if df.empty:
        print("No valid numeric data in 'points' column after cleaning.")
        return

    # --- Store original scores for report if adjustments are made later ---
    df['points_raw_original_for_report'] = df['points_numeric'].copy()
    df['score_0_10_original_for_report'] = (df['points_raw_original_for_report'] / max_score) * 10
    df['score_0_10_original_clipped_for_report'] = np.clip(df['score_0_10_original_for_report'], 0, 10)

    # --- Process voided questions ---
    void_q_list = parse_q_list(void_questions_str)
    nice_q_list_initial = parse_q_list(void_questions_nicely_str)
    # Ensure nice_q_list does not overlap with void_q_list (void takes precedence)
    nice_q_list = [q for q in nice_q_list_initial if q not in void_q_list]

    adjustments_made = bool(void_q_list or nice_q_list)

    points_for_scaling = df['points_numeric'].copy()
    # Initialize max_score_for_scaling as a Series
    max_score_for_scaling = pd.Series([float(max_score)] * len(df), index=df.index)

    if adjustments_made:
        logging.info("Applying question adjustments...")
        for q_num in void_q_list:
            points_col_name = f'points.{q_num}'
            if points_col_name in df.columns:
                logging.info(f"Voiding question {q_num}: Removing points and reducing max score by 1.")
                # Ensure points for this question are numeric before subtraction
                q_points_numeric = pd.to_numeric(df[points_col_name], errors='coerce').fillna(0)
                points_for_scaling -= q_points_numeric
                max_score_for_scaling -= 1.0
            else:
                logging.warning(f"Cannot void question {q_num}: Column '{points_col_name}' not found.")

        for q_num in nice_q_list:
            points_col_name = f'points.{q_num}'
            if points_col_name in df.columns:
                logging.info(f"Nicely voiding question {q_num} for incorrect/NA answers.")
                q_points_numeric = pd.to_numeric(df[points_col_name], errors='coerce').fillna(0)
                condition_incorrect_or_na = q_points_numeric <= 0
                
                # Subtract points (if negative, this adds back penalty; if 0, no change)
                points_for_scaling.loc[condition_incorrect_or_na] -= q_points_numeric.loc[condition_incorrect_or_na]
                # Reduce max score for these students for this question
                max_score_for_scaling.loc[condition_incorrect_or_na] -= 1.0
            else:
                logging.warning(f"Cannot 'nicely' void question {q_num}: Column '{points_col_name}' not found.")
        
        df['points_adjusted_for_report'] = points_for_scaling.copy()
        df['max_score_adjusted_for_report'] = max_score_for_scaling.copy()


    # Scale scores to 0-10 range using potentially adjusted points and max_score
    # df['score_0_10'] will store the (potentially adjusted) final scaled score
    df['score_0_10'] = (points_for_scaling / max_score_for_scaling.where(max_score_for_scaling > 0, np.nan)) * 10
    
    # Clip scores to be within 0 and 10 (or slightly above 10 if points can exceed max_score significantly)
    # If scores are strictly capped at max_score, then this will cap scaled scores at 10.
    # If bonus points can make points > max_score, then scaled scores can be > 10.
    # The histogram bins [10, 11) will capture scores of exactly 10.
    # For scores > 10, they will fall into the last bin if its upper range is high enough, or be clipped.
    # We'll clip at 10.0 for display purposes in stats, but allow histogram to show actual distribution.
    # Let's make bins explicit: [0,1,2,3,4,5,6,7,8,9,10,11] to create 11 bars for [0,1), [1,2)...[10,11)
    
    df['score_0_10_clipped_for_stats'] = np.clip(df['score_0_10'], 0, 10)


    print("\n--- Descriptive Statistics for Scores (0-10 scale) ---")
    # Show stats for the version clipped at 10 for clearer interpretation
    stats = df['score_0_10_clipped_for_stats'].describe() 
    print(stats)
    
    # --- Plotting ---
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 7)) # Slightly wider for 11 bars

    # For plotting, discretize scores into integer bins (0, 1, ..., 10)
    # A score 's' maps to an integer bin 'b = floor(s + 0.5)'.
    # This means:
    #   - scores in [-0.5, 0.5) map to bin 0
    #   - scores in [0.5, 1.5) map to bin 1
    #   - ...
    #   - scores in [7.5, 8.5) map to bin 8
    #   - ...
    #   - scores in [9.5, 10.5) map to bin 10 (assuming scores are clipped at 10, floor(10.0 + 0.5) = 10)
    # This aligns with the bar for score X covering the visual range [X-0.5, X+0.5].
    # Use the (potentially adjusted) score_0_10_clipped_for_stats for binning
    df['score_binned_for_plot'] = np.floor(df['score_0_10_clipped_for_stats'].fillna(0) + 0.5).astype(int)


    # 1. Calculate frequencies for scores 0 through 10 using the binned scores
    #    This ensures all scores in the range are represented, even with a count of 0.
    score_counts = Counter(df['score_binned_for_plot']) # Use the new binned scores
    all_possible_scores = np.arange(0, 11) # Integer scores from 0 to 10
    frequencies = [score_counts.get(s, 0) for s in all_possible_scores]

    # 2. Generate the bar plot
    #    width=1.0 makes bars touch.
    #    align='center' ensures bars are centered on the integer scores.
    #    For a score 's', the bar will span from s-0.5 to s+0.5.
    plt.bar(all_possible_scores, frequencies, width=1.0, edgecolor='black', align='center', color='skyblue')

    # 3. Set title and labels
    ax.set_title(f'Distribution of Exam Scores (Scaled to 0-10 from Max Raw: {max_score})', fontsize=15)
    ax.set_xlabel('Score (0-10 Scale)', fontsize=12)
    ax.set_ylabel('Number of Students', fontsize=12)

    # 4. Configure x-axis ticks and limits
    #    Set x-axis ticks to be integers from 0 to 10.
    ax.set_xticks(np.arange(0, 11, 1))
    #    Set x-axis limits to show the full bars for 0 (from -0.5 to 0.5)
    #    and 10 (from 9.5 to 10.5) without -0.5 and 10.5 appearing as tick labels.
    ax.set_xlim(-0.5, 10.5)

    # 5. Adjust y-axis for better appearance
    ax.set_ylim(bottom=0) # Ensure y-axis starts at 0
    # Add some padding to the top of the y-axis
    if max(frequencies, default=0) > 0: # Use default for max() in case frequencies is empty or all zeros
        ax.set_ylim(top=max(frequencies) * 1.1)
    else:
        ax.set_ylim(top=1) # Default top if no data or all zeros, to show an empty plot area

    # 6. Optional: Add a horizontal grid for readability
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    mean_score = df['score_0_10_clipped_for_stats'].mean() # Use clipped for mean line for consistency with stats
    median_score = df['score_0_10_clipped_for_stats'].median()
    ax.axvline(mean_score, color='red', linestyle='dashed', linewidth=1.5, label=f'Mean: {mean_score:.2f}')
    ax.axvline(median_score, color='green', linestyle='dashed', linewidth=1.5, label=f'Median: {median_score:.2f}')
    ax.legend()

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    plot_filename = os.path.join(output_dir, "score_distribution_0_10.png")
    try:
        plt.savefig(plot_filename)
        print(f"\nPlot saved to {os.path.abspath(plot_filename)}")
    except Exception as e:
        print(f"Error saving plot: {e}")

    print("\n--- Additional Statistics (0-10 scale) ---")
    passing_threshold_0_10 = 5.0
    num_passed = df[df['score_0_10_clipped_for_stats'] >= passing_threshold_0_10].shape[0]
    total_students = df.shape[0]
    pass_rate = (num_passed / total_students) * 100 if total_students > 0 else 0
    print(f"Number of students: {total_students}")
    print(f"Number of students passed (score >= {passing_threshold_0_10}): {num_passed} ({pass_rate:.2f}%)")

    # Display raw points based on whether adjustments were made
    if adjustments_made:
        print(f"Adjusted raw score range (points_adjusted): {points_for_scaling.min():.2f} - {points_for_scaling.max():.2f} (out of effective max {max_score_for_scaling.min() if max_score_for_scaling.nunique() > 1 else max_score_for_scaling.unique()[0] if max_score_for_scaling.nunique() == 1 else 'N/A'} to {max_score_for_scaling.max()})")
        print(f"Original raw score range (points): {df['points_raw_original_for_report'].min():.2f} - {df['points_raw_original_for_report'].max():.2f} (out of original max {max_score})")
    else:
        print(f"Raw score range (points): {df['points_numeric'].min():.2f} - {df['points_numeric'].max():.2f} (out of {max_score})")
    
    # For score_0_10, show actual min/max before clipping for stats to understand full range if scores > 10
    # This 'score_0_10' is now the potentially adjusted one
    print(f"Scaled score (0-10 actual) range: {df['score_0_10'].min():.2f} - {df['score_0_10'].max():.2f}")

    # --- Print Student Marks (Alphabetical Order) ---
    print("\n--- Student Marks (Alphabetical Order, 0-10 Scale) ---")
    can_print_student_list = False
    pln_student_list_path = ""

    if 'registration' in df.columns: # Proceed only if registration column is available for merging
        # Try to determine path for pln_2025.csv
        # Assumes csv_filepath is like '.../generated/splits/some_subdir/results.csv'
        # and pln_2025.csv is in '.../generated/splits/pln_2025.csv'
        try:
            grandparent_dir_of_csv = os.path.dirname(os.path.dirname(csv_filepath))
            pln_filename = "pln_2025.csv"
            # Construct a plausible path based on common project structure
            # Example: if csv_filepath is C:/Users/Oscar/AutoTestIA/generated/splits/final_rexams_corrected/exam_corrected_results.csv
            # grandparent_dir_of_csv would be C:/Users/Oscar/AutoTestIA/generated/splits
            potential_pln_path = os.path.join(grandparent_dir_of_csv, pln_filename)

            # Check if the AutoTestIA workspace root can be found to build a more robust relative path
            # This part is a bit heuristic; an explicit path argument would be more robust.
            # Assuming the script is run from a context where 'generated/splits/pln_2025.csv' is valid
            # For now, let's try the potential_pln_path. If not found, use a fixed relative path from common workspace root.
            # This relies on a typical project structure.
            # A simpler approach if script is run from AutoTestIA root:
            fixed_relative_pln_path = os.path.join("generated", "splits", "pln_2025.csv")

            if os.path.exists(potential_pln_path):
                 pln_student_list_path = potential_pln_path
            elif os.path.exists(fixed_relative_pln_path):
                 pln_student_list_path = fixed_relative_pln_path
            else: # Try to find it next to the input CSV as a last resort (less likely structure)
                pln_student_list_path_alt = os.path.join(os.path.dirname(csv_filepath), pln_filename)
                if os.path.exists(pln_student_list_path_alt):
                    pln_student_list_path = pln_student_list_path_alt

            if os.path.exists(pln_student_list_path):
                can_print_student_list = True
            else:
                print(f"Warning: Student list file '{pln_filename}' not found. Tried paths based on '{csv_filepath}' structure and common '{fixed_relative_pln_path}'.")
                print(f"Searched for: {potential_pln_path}, {fixed_relative_pln_path}" + (f", {pln_student_list_path_alt}" if 'pln_student_list_path_alt' in locals() and pln_student_list_path_alt else "") + ".")
                print(f"Cannot print student names and marks.")
        except Exception as path_ex:
            print(f"Error determining path for pln_2025.csv: {path_ex}")
            print(f"Cannot print student names and marks.")

    if can_print_student_list and 'registration' in df.columns:
        try:
            students_info_df = pd.read_csv(pln_student_list_path, usecols=['DNI', 'Nom', 'Cognoms'], dtype={'DNI': str}, sep=',')
            students_info_df.rename(columns={'DNI': 'registration_original_pln', 'Nom': 'FirstName', 'Cognoms': 'Surnames'}, inplace=True)

            # Prepare merge keys
            df['merge_key'] = df['registration'].astype(str).str.strip()
            students_info_df['merge_key'] = students_info_df['registration_original_pln'].astype(str).str.strip().str.lstrip('0')
            
            # Select necessary columns for student list
            cols_for_student_list = ['merge_key', 'registration']
            rename_map_for_student_list = {'registration': 'registration_from_exam_results'}

            if adjustments_made:
                cols_for_student_list.extend([
                    'score_0_10_original_clipped_for_report',
                    'points_raw_original_for_report',
                    'score_0_10_clipped_for_stats', # This is the adjusted one for stats
                    'points_adjusted_for_report',
                    'max_score_adjusted_for_report'
                ])
                rename_map_for_student_list.update({
                    'score_0_10_original_clipped_for_report': 'OriginalScaledScore',
                    'points_raw_original_for_report': 'OriginalRawPoints',
                    'score_0_10_clipped_for_stats': 'AdjustedScaledScore',
                    'points_adjusted_for_report': 'AdjustedRawPoints',
                    'max_score_adjusted_for_report': 'AdjustedMaxScorePossible'
                })
            else:
                cols_for_student_list.extend([
                    'score_0_10_clipped_for_stats', # This is the main (and only) scaled score
                    'points_numeric'                # This is the main (and only) raw score
                ])
                rename_map_for_student_list.update({
                    'score_0_10_clipped_for_stats': 'ScaledScore',
                    'points_numeric': 'RawPoints'
                })
            
            exam_scores_df = df[cols_for_student_list].copy()
            exam_scores_df.rename(columns=rename_map_for_student_list, inplace=True)
            
            students_info_to_merge = students_info_df[['merge_key', 'FirstName', 'Surnames', 'registration_original_pln']].copy()
            merged_students_df = pd.merge(exam_scores_df, students_info_to_merge, on='merge_key', how='left')

            merged_students_df['FormattedName'] = np.where(
                merged_students_df['FirstName'].notna() & merged_students_df['Surnames'].notna(),
                merged_students_df['Surnames'] + ", " + merged_students_df['FirstName'],
                "Unknown Student (Registration: " + merged_students_df['registration_from_exam_results'].astype(str) + ")"
            )
            
            # Select columns for printing
            # The specific score column for 'SortableName' and printing depends on adjustments_made
            final_cols_for_print = ['FormattedName']
            if adjustments_made:
                final_cols_for_print.extend(['OriginalScaledScore', 'OriginalRawPoints', 
                                             'AdjustedScaledScore', 'AdjustedRawPoints', 'AdjustedMaxScorePossible'])
            else:
                final_cols_for_print.extend(['ScaledScore', 'RawPoints'])

            results_to_print_df = merged_students_df[final_cols_for_print].copy()
            
            results_to_print_df['SortableName'] = results_to_print_df['FormattedName'].apply(
                lambda x: unidecode.unidecode(str(x)).lower()
            )
            results_to_print_df.sort_values(by='SortableName', inplace=True)

            original_overall_max_score = float(max_score)

            if results_to_print_df.empty:
                print("No student data available to display for the marks list.")
            else:
                table_data = []
                headers = ["Student Name"]
                if adjustments_made:
                    headers.extend([
                        "Adjusted Score (0-10)", "Original Score (0-10)",
                        "Adjusted Raw Points", "Adjusted Max Points",
                        "Original Raw Points", "Original Max Points"
                    ])
                else:
                    headers.extend(["Scaled Score (0-10)", "Raw Points", "Max Points"])

                for _, row in results_to_print_df.iterrows():
                    name = row['FormattedName']
                    row_data = [name]
                    if adjustments_made and 'AdjustedScaledScore' in row and 'OriginalScaledScore' in row:
                        original_scaled = row['OriginalScaledScore']
                        adjusted_scaled = row['AdjustedScaledScore']
                        original_raw = row['OriginalRawPoints']
                        adjusted_raw = row['AdjustedRawPoints']
                        adjusted_max_student = row['AdjustedMaxScorePossible']

                        adj_scaled_is_nan = pd.isna(adjusted_scaled)
                        orig_scaled_is_nan = pd.isna(original_scaled)
                        
                        adj_scaled_str = f"{adjusted_scaled:.2f}" if not adj_scaled_is_nan else "N/A"
                        orig_scaled_str = f"{original_scaled:.2f}" if not orig_scaled_is_nan else "N/A"
                        adj_raw_str = f"{adjusted_raw:.2f}" if not pd.isna(adjusted_raw) else "N/A"
                        adj_max_str = f"{adjusted_max_student:.2f}" if not pd.isna(adjusted_max_student) else "N/A"
                        orig_raw_str = f"{original_raw:.2f}" if not pd.isna(original_raw) else "N/A"
                        orig_max_str = f"{original_overall_max_score:.2f}"

                        changed = False
                        if adj_scaled_is_nan != orig_scaled_is_nan:
                            changed = True
                        elif not adj_scaled_is_nan and not orig_scaled_is_nan and not np.isclose(original_scaled, adjusted_scaled):
                            changed = True

                        if changed:
                            row_data.extend([
                                adj_scaled_str, orig_scaled_str,
                                adj_raw_str, adj_max_str,
                                orig_raw_str, orig_max_str
                            ])
                        else: # Score didn't change, or only one set of scores is relevant (e.g. only adjusted makes sense)
                            row_data.extend([
                                adj_scaled_str, "-", # Indicate original is same or not applicable to show separately
                                adj_raw_str, adj_max_str,
                                "-", "-" # Original raw/max not shown if score unchanged
                            ])
                    
                    elif 'ScaledScore' in row and 'RawPoints' in row: # No adjustments
                        scaled_score_val = row['ScaledScore']
                        raw_points_val = row['RawPoints']
                        scaled_str = f"{scaled_score_val:.2f}" if not pd.isna(scaled_score_val) else "N/A"
                        raw_str = f"{raw_points_val:.2f}" if not pd.isna(raw_points_val) else "N/A"
                        orig_max_str = f"{original_overall_max_score:.2f}"
                        row_data.extend([scaled_str, raw_str, orig_max_str])
                    else:
                        # Fallback if somehow columns are missing
                        score_display_val = row.get('AdjustedScaledScore', row.get('ScaledScore', float('nan')))
                        score_display_str = f"{score_display_val:.2f}" if not pd.isna(score_display_val) else "N/A"
                        if adjustments_made:
                             row_data.extend([score_display_str, "N/A", "N/A", "N/A", "N/A", "N/A"])
                        else:
                             row_data.extend([score_display_str, "N/A", "N/A"])
                    table_data.append(row_data)
                
                print(tabulate(table_data, headers=headers, floatfmt=".2f"))

        except FileNotFoundError:
             print(f"Error: The student information file ({pln_student_list_path}) was not found during the student marks listing.")
        except Exception as e:
            print(f"Error processing student list for marks display: {e}")
    elif 'registration' not in df.columns:
         pass # Warning already printed
    # else: can_print_student_list is False, warning already printed

    # --- Per-Question Response Distribution Plot ---
    logging.info("\n--- Generating Per-Question Response Distribution Plots ---")
    answer_cols = sorted([col for col in df.columns if col.startswith('answer.') and '.' in col and col.split('.')[1].isdigit()], key=lambda x: int(x.split('.')[1]))
    solution_cols = sorted([col for col in df.columns if col.startswith('solution.') and '.' in col and col.split('.')[1].isdigit()], key=lambda x: int(x.split('.')[1]))

    if not answer_cols or not solution_cols:
        logging.warning("Could not find answer/solution columns for per-question response plot. Skipping this plot.")
    elif len(answer_cols) != len(solution_cols):
        logging.warning(f"Mismatch between number of answer ({len(answer_cols)}) and solution ({len(solution_cols)}) columns. Skipping per-question plot.")
    else:
        num_questions = len(answer_cols)
        num_actual_choices = 0 # This will be derived from solution strings (e.g., 4)
        fixed_answer_string_length = 0 # This will be derived from answer strings (e.g., 5)

        try:
            # Determine fixed_answer_string_length from answer.X columns
            for ans_col_to_check in answer_cols:
                valid_answer_series = df[ans_col_to_check].dropna()
                if not valid_answer_series.empty:
                    for ans_str_val in valid_answer_series:
                        processed_ans_str = str(ans_str_val).strip()
                        if processed_ans_str and processed_ans_str.lower() != 'nan' and all(c in '01' for c in processed_ans_str) and len(processed_ans_str) > 1:
                            fixed_answer_string_length = len(processed_ans_str)
                            break
                if fixed_answer_string_length > 0:
                    logging.info(f"Determined fixed student answer string length as {fixed_answer_string_length} from column '{ans_col_to_check}'.")
                    break
            if fixed_answer_string_length == 0:
                raise ValueError("Could not determine the fixed length of student answer strings (e.g., 5 chars) from any answer.X column.")

            # Determine num_actual_choices from solution.X columns
            for sol_col_to_check in solution_cols:
                valid_solution_series = df[sol_col_to_check].dropna()
                if not valid_solution_series.empty:
                    for sol_str_val in valid_solution_series:
                        processed_sol_str = str(sol_str_val).strip()
                        if processed_sol_str and processed_sol_str.lower() != 'nan' and all(c in '01' for c in processed_sol_str) and len(processed_sol_str) > 0:
                            # Check that this solution length is not greater than the answer string length
                            if len(processed_sol_str) <= fixed_answer_string_length:
                                num_actual_choices = len(processed_sol_str)
                                break
                            else:
                                logging.warning(f"Solution string '{processed_sol_str}' in {sol_col_to_check} is longer ({len(processed_sol_str)}) than answer strings ({fixed_answer_string_length}). This is unexpected. Skipping this solution string.")
                    if num_actual_choices > 0: # check if break from inner loop happened
                        break 
                if num_actual_choices > 0:
                    logging.info(f"Determined actual number of choices for scoring/plotting as {num_actual_choices} from solution column '{sol_col_to_check}'.")
                    break
            
            if num_actual_choices == 0:
                 raise ValueError("Could not determine the actual number of choices (e.g., 4) from any solution.X column (or they were invalid/longer than answer strings).")

        except (IndexError, ValueError) as e:
            logging.warning(f"Could not reliably determine number of choices from solution columns: {e}. Skipping per-question plot.")
            # num_actual_choices remains 0, so the next block will be skipped.

        if num_actual_choices > 0:
            all_question_stats = []
            for i in range(num_questions):
                ans_col = answer_cols[i]
                sol_col = solution_cols[i]
                # Extract question number, assuming format "answer.X" or "solution.X"
                try:
                    q_num = int(ans_col.split('.')[1])
                except (IndexError, ValueError):
                    logging.warning(f"Could not parse question number from column {ans_col}. Skipping this column for plot.")
                    continue

                valid_solutions = df[sol_col].dropna()
                if valid_solutions.empty:
                    logging.warning(f"No valid solution string found for question {q_num} ({sol_col}). Skipping this question for plot.")
                    continue
                
                correct_solution_str = str(valid_solutions.iloc[0]).strip()
                # Solution string MUST match num_actual_choices derived from solution columns overall
                if not (isinstance(correct_solution_str, str) and len(correct_solution_str) == num_actual_choices and all(c in '01' for c in correct_solution_str)):
                    logging.warning(f"Q{q_num}: Solution string '{correct_solution_str}' from column {sol_col} is invalid or its length ({len(correct_solution_str)}) doesn't match expected num_actual_choices ({num_actual_choices}). Setting correct_idx to -1.")
                    correct_choice_idx = -1 # Explicitly set to -1 if solution string is bad
                    # continue # Don't skip the question, just mark as no correct answer for plotting
                else:
                    # Solution string seems valid, try to find the correct choice
                    if '1' in correct_solution_str:
                        correct_choice_idx = correct_solution_str.find('1')
                        if correct_solution_str.count('1') > 1:
                            logging.warning(f"Q{q_num}: Multiple correct answers indicated in solution string '{correct_solution_str}'. Using first one found at index {correct_choice_idx} for coloring.")
                    else:
                        correct_choice_idx = -1 # No '1' found in an otherwise valid-looking solution string
                
                # logging.debug(f"DEBUG Q{q_num} (sol_col: {sol_col}): Parsed correct_solution_str='{correct_solution_str}', num_actual_choices={num_actual_choices}, Derived correct_choice_idx={correct_choice_idx}")

                response_counts = [0] * (num_actual_choices + 1)  # +1 for "Not Answered"

                for answer_str_val in df[ans_col]:
                    # Ensure conversion to string first, then strip whitespace
                    processed_ans_str = str(answer_str_val).strip()

                    # Check for various forms of "Not Answered" or invalid/empty strings
                    if not processed_ans_str or processed_ans_str.lower() == 'nan':
                        response_counts[num_actual_choices] += 1 # NA index is num_actual_choices
                        continue
                    
                    # Student answer strings have a fixed length (e.g., 5), but we only care about the first num_actual_choices (e.g., 4) for selection
                    if len(processed_ans_str) != fixed_answer_string_length:
                        # logging.debug(f"Q{q_num}: Student answer string '{processed_ans_str}' (original value: '{answer_str_val}') length ({len(processed_ans_str)}) does not match expected fixed answer string length ({fixed_answer_string_length}). Treating as NA.")
                        response_counts[num_actual_choices] += 1 # NA
                        continue

                    # Consider only the relevant part of the answer string based on num_actual_choices
                    relevant_answer_part = processed_ans_str[:num_actual_choices]

                    if '1' not in relevant_answer_part:
                        response_counts[num_actual_choices] += 1  # NA
                    else:
                        if relevant_answer_part.count('1') > 1:
                            # logging.debug(f"Q{q_num}: Student answer relevant part '{relevant_answer_part}' (from '{processed_ans_str}') has multiple selections. Counting first one found.")
                            pass # Added pass to maintain block structure
                        try:
                            selected_idx = relevant_answer_part.find('1')
                            # selected_idx is within the bounds of the relevant_answer_part (0 to num_actual_choices-1)
                            if 0 <= selected_idx < num_actual_choices: 
                                response_counts[selected_idx] += 1
                            else: 
                                # This case should ideally not be hit if .find('1') worked and '1' was in relevant_answer_part
                                # logging.debug(f"Q{q_num}: Invalid selected index {selected_idx} from relevant part '{relevant_answer_part}' (from '{processed_ans_str}'). Treating as NA.")
                                response_counts[num_actual_choices] += 1 # NA
                                pass # Added pass to maintain block structure
                        except Exception as e_parse_ans: 
                            # logging.warning(f"Q{q_num}: Error parsing student answer relevant part '{relevant_answer_part}' (from '{processed_ans_str}'): {e_parse_ans}. Treating as NA.")
                            response_counts[num_actual_choices] += 1

                all_question_stats.append({
                    'q_num': q_num,
                    'counts': response_counts, # response_counts has num_actual_choices + 1 elements
                    'correct_idx': correct_choice_idx, # correct_choice_idx is 0 to num_actual_choices-1
                    'num_actual_choices': num_actual_choices # This is the key for plotting (e.g. 4)
                })
            
            # Plotting the collected stats
            if all_question_stats:
                questions_per_ax_subplot = 10 # Number of questions to group into one Axes object/subplot row
                num_total_questions_with_stats = len(all_question_stats)
                
                num_axes_subplots_rows = int(np.ceil(num_total_questions_with_stats / questions_per_ax_subplot))

                if num_axes_subplots_rows > 0:
                    # Adjust height: each subplot row contributes ~3 inches. Min total height 3.
                    fig_total_height = max(3, num_axes_subplots_rows * 3) 
                    fig_width = 18 

                    fig, axes_array = plt.subplots(nrows=num_axes_subplots_rows, ncols=1, 
                                             figsize=(fig_width, fig_total_height), squeeze=False) 

                    # fig.suptitle("Per-Question Student Response Distributions", fontsize=18, y=0.99) # REMOVED Overall title

                    for i_ax_row in range(num_axes_subplots_rows):
                        ax = axes_array[i_ax_row, 0] # Get the current Axes object for this row/subplot

                        start_q_data_idx = i_ax_row * questions_per_ax_subplot
                        end_q_data_idx = min((i_ax_row + 1) * questions_per_ax_subplot, num_total_questions_with_stats)
                        current_ax_q_data_list = all_question_stats[start_q_data_idx:end_q_data_idx]

                        if not current_ax_q_data_list:
                            continue 
                        
                        num_q_in_this_ax = len(current_ax_q_data_list)
                        # All q_data in current_ax_q_data_list will have the same num_actual_choices.
                        current_plot_num_choices = current_ax_q_data_list[0]['num_actual_choices'] 

                        bar_group_total_width_ratio = 0.8 
                        num_bars_per_group = current_plot_num_choices + 1 
                        single_bar_width = bar_group_total_width_ratio / num_bars_per_group
                        
                        question_group_centers_x = np.arange(num_q_in_this_ax)

                        for q_plot_idx, q_data in enumerate(current_ax_q_data_list):
                            counts = q_data['counts']
                            # Ensure correct_solution_str is re-checked here for the specific question's data
                            # It seems q_data already has 'correct_idx' and 'num_actual_choices'
                            # The 'correct_idx' should be derived when all_question_stats is populated.

                            bar_colors_for_q = ['#d62728'] * current_plot_num_choices + ['#7f7f7f'] 
                            # Re-confirming correct_idx is valid for this question's choices
                            if 0 <= q_data['correct_idx'] < current_plot_num_choices:
                                bar_colors_for_q[q_data['correct_idx']] = '#2ca02c' 
                                # logging.debug(f"DEBUG Q{q_data['q_num']}: Applied GREEN. correct_idx={q_data['correct_idx']}, current_plot_num_choices={current_plot_num_choices}, bar_colors_for_q={bar_colors_for_q}") # DETAILED DEBUG
                            else:
                                # This case implies the correct_idx was -1 or out of bounds for current_plot_num_choices
                                # This can happen if the solution string for a question was all '0's or invalid
                                # No green bar will be shown, which is correct if no single correct choice was identifiable
                                # logging.debug(f"Q{q_data['q_num']}: No valid correct_idx ({q_data['correct_idx']}) for coloring green bar. current_plot_num_choices={current_plot_num_choices}")
                                pass # Added pass to maintain block structure

                            group_center_x = question_group_centers_x[q_plot_idx]
                            start_x_for_bar_group = group_center_x - (bar_group_total_width_ratio / 2.0)

                            for choice_bar_k in range(num_bars_per_group):
                                bar_x_center = start_x_for_bar_group + (choice_bar_k * single_bar_width)
                                ax.bar(bar_x_center, counts[choice_bar_k], width=single_bar_width * 0.95,
                                       color=bar_colors_for_q[choice_bar_k], edgecolor='black', linewidth=0.5)

                        ax.set_ylabel('Number of Students', fontsize=12)
                        q_start_num_disp = current_ax_q_data_list[0]['q_num']
                        q_end_num_disp = current_ax_q_data_list[-1]['q_num']
                        ax.set_title(f'Questions {q_start_num_disp}-{q_end_num_disp}', fontsize=15, pad=20)
                        
                        ax.set_xticks(question_group_centers_x)
                        ax.set_xticklabels([f"Q{q_d['q_num']}" for q_d in current_ax_q_data_list], fontsize=10, rotation=45, ha="right")
                        ax.tick_params(axis='x', which='major', pad=7)

                        max_count_on_plot = 0
                        for q_data in current_ax_q_data_list:
                            current_max = max(q_data['counts']) if q_data['counts'] else 0
                            if current_max > max_count_on_plot:
                                max_count_on_plot = current_max
                        
                        if max_count_on_plot > 0 :
                            ax.set_ylim(top=max_count_on_plot * 1.15) 
                            if max_count_on_plot <= 20: 
                                 ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

                        # Display legend only for the first subplot (top one), inside the plot area
                        if i_ax_row == 0:
                            legend_handles = [
                                plt.Rectangle((0,0),1,1, color='#2ca02c', label='Correct Choice'),
                                plt.Rectangle((0,0),1,1, color='#d62728', label='Incorrect Choice'),
                                plt.Rectangle((0,0),1,1, color='#7f7f7f', label='Not Answered')
                            ]
                            
                            choice_labels_for_legend = [chr(ord('A') + k) for k in range(current_plot_num_choices)] + ['NA']
                            bar_order_info_text = "Bar order for each Q: " + " / ".join(choice_labels_for_legend)
                            
                            empty_artist = plt.Rectangle((0,0),0,0,alpha=0.0, label=bar_order_info_text) 
                            legend_handles.append(empty_artist)

                            # Place legend inside the subplot, e.g., upper right or let matplotlib decide with 'best'
                            ax.legend(handles=legend_handles, title="Legend", loc='upper right', fontsize='small') # Changed loc and added fontsize
                    
                    # Adjust layout to prevent overlap 
                    # Removed right padding adjustment for legend as it's now inside
                    plt.tight_layout(rect=[0, 0, 1, 0.97]) # rect: [left, bottom, right, top adjusted for subplot titles]
                    
                    plot_filename_dist = os.path.join(output_dir, "all_question_response_distributions.png")
                    try:
                        plt.savefig(plot_filename_dist) # bbox_inches='tight' removed as tight_layout is used.
                        logging.info(f"Combined per-question response plot saved to {os.path.abspath(plot_filename_dist)}")
                    except Exception as e_save:
                        logging.error(f"Error saving combined per-question response plot '{plot_filename_dist}': {e_save}")
                    plt.close(fig)
                else:
                    logging.info("No question data rows to plot for response distribution.")
            else:
                logging.info("No valid question data was processed to generate response distribution plots.")
        else:
            # This case is when num_actual_choices <= 0 after trying to determine it
            logging.info("Skipping per-question response plot as number of choices could not be determined or was zero.")
    # --- End of Per-Question Response Distribution Plot ---


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze exam results, scale scores to 0-10, plot distribution, and show statistics.")
    parser.add_argument("--results-csv", required=True,
                        help="Path to the exam_corrected_results.csv file.")
    parser.add_argument("--max-score", type=float, required=True,
                        help="Maximum possible raw score for the exam (e.g., 30 for 30 raw points).")
    parser.add_argument("--output-plot-dir", default="exam_analysis_plots",
                        help="Directory to save the generated plot(s). Default: 'exam_analysis_plots'")
    parser.add_argument("--void-questions", type=str, default=None,
                        help="Comma-separated list of question numbers to remove from score calculation (e.g., '3,4').")
    parser.add_argument("--void-questions-nicely", type=str, default=None,
                        help="Comma-separated list of question numbers to void if incorrect/NA, count if correct (e.g., '5,6').")
    
    args = parser.parse_args()

    analyze_results(csv_filepath=args.results_csv, 
                    max_score=args.max_score, 
                    output_dir=args.output_plot_dir,
                    void_questions_str=args.void_questions,
                    void_questions_nicely_str=args.void_questions_nicely) 