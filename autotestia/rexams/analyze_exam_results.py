import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os
import numpy as np
from collections import Counter
import unidecode # For improved alphabetical sorting

def analyze_results(csv_filepath, max_score, output_dir="."):
    """
    Analyzes exam results from a CSV file, scales scores to 0-10, 
    plots score distribution with 11 specific bars, and shows statistics.

    Args:
        csv_filepath (str): Path to the exam results CSV file.
        max_score (float): The maximum possible raw score for the exam (for normalization).
        output_dir (str): Directory to save the output plot.
    """
    if not os.path.exists(csv_filepath):
        print(f"Error: CSV file not found at {csv_filepath}")
        return

    try:
        df = pd.read_csv(csv_filepath, sep=';', decimal='.')
        print(f"Successfully loaded {csv_filepath}")
        print(f"Columns found: {df.columns.tolist()}")
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
        
    # Scale scores to 0-10 range
    df['score_0_10'] = (df['points_numeric'] / max_score) * 10
    
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
    df['score_binned_for_plot'] = np.floor(df['score_0_10_clipped_for_stats'] + 0.5).astype(int)
    # Ensure bins are within the 0-10 range, especially if original scores could be slightly outside
    # due to floating point issues before clipping, though df['score_0_10_clipped_for_stats'] handles this.
    df['score_binned_for_plot'] = np.clip(df['score_binned_for_plot'], 0, 10)


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

    print(f"Raw score range (points): {df['points_numeric'].min():.2f} - {df['points_numeric'].max():.2f}")
    # For score_0_10, show actual min/max before clipping for stats to understand full range if scores > 10
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
            # Key from exam_corrected_results.csv (df): strip spaces. This is what's shown in "Unknown Student (Registration: XXX)"
            df['merge_key'] = df['registration'].astype(str).str.strip()
            
            # Key from pln_2025.csv (students_info_df): strip spaces and leading zeros from DNI.
            students_info_df['merge_key'] = students_info_df['registration_original_pln'].astype(str).str.strip().str.lstrip('0')
            
            # Select only necessary columns before merge to avoid duplicate 'registration' columns if names were the same
            exam_scores_df = df[['merge_key', 'registration', 'score_0_10_clipped_for_stats']].copy()
            # Rename the original registration from df to avoid conflict if we were to merge on 'registration' directly
            exam_scores_df.rename(columns={'registration': 'registration_from_exam_results'}, inplace=True)

            students_info_to_merge = students_info_df[['merge_key', 'FirstName', 'Surnames', 'registration_original_pln']].copy()

            merged_students_df = pd.merge(exam_scores_df, students_info_to_merge, on='merge_key', how='left')

            # Create formatted name: "Surnames, FirstName"
            # Use 'registration_from_exam_results' for the "Unknown Student" message, as that's the ID from the results file.
            merged_students_df['FormattedName'] = np.where(
                merged_students_df['FirstName'].notna() & merged_students_df['Surnames'].notna(),
                merged_students_df['Surnames'] + ", " + merged_students_df['FirstName'],
                "Unknown Student (Registration: " + merged_students_df['registration_from_exam_results'].astype(str) + ")"
            )
            
            results_to_print_df = merged_students_df[['FormattedName', 'score_0_10_clipped_for_stats']].copy()
            results_to_print_df.rename(columns={'score_0_10_clipped_for_stats': 'ScaledScore_0_10'}, inplace=True)
            
            # Create a sortable name using unidecode to handle accents correctly for sorting
            results_to_print_df['SortableName'] = results_to_print_df['FormattedName'].apply(
                lambda x: unidecode.unidecode(str(x)).lower() # Ensure it's a string and use lower for case-insensitivity
            )
            results_to_print_df.sort_values(by='SortableName', inplace=True)

            if results_to_print_df.empty:
                print("No student data available to display for the marks list.")
            else:
                for _, row in results_to_print_df.iterrows():
                    print(f"{row['FormattedName']}: {row['ScaledScore_0_10']:.2f}")

        except FileNotFoundError:
             print(f"Error: The student information file ({pln_student_list_path}) was not found during the student marks listing.")
        except Exception as e:
            print(f"Error processing student list for marks display: {e}")
    elif 'registration' not in df.columns:
         pass # Warning already printed
    # else: can_print_student_list is False, warning already printed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze exam results, scale scores to 0-10, plot distribution, and show statistics.")
    parser.add_argument("--results-csv", required=True,
                        help="Path to the exam_corrected_results.csv file.")
    parser.add_argument("--max-score", type=float, required=True,
                        help="Maximum possible raw score for the exam (e.g., 30 for 30 raw points).")
    parser.add_argument("--output-plot-dir", default="exam_analysis_plots",
                        help="Directory to save the generated plot(s). Default: 'exam_analysis_plots'")
    
    args = parser.parse_args()

    analyze_results(csv_filepath=args.results_csv, 
                    max_score=args.max_score, 
                    output_dir=args.output_plot_dir) 