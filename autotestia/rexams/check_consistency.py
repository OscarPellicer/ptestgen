import csv
import os

try:
    import Levenshtein # For suggesting similar DNIs
except ImportError:
    print("WARNING: The 'Levenshtein' package is not installed. DNI similarity suggestions will not be available.")
    print("You can install it by running: pip install python-Levenshtein")
    Levenshtein = None # So we can check its availability later

def check_student_data_consistency(pln_path, daten_path, processed_path):
    """
    Checks for inconsistencies between student registration lists and scanned exam data.
    Includes suggestions for similar DNIs if an exact match is not found.

    Args:
        pln_path (str): Path to the pln_2025.csv file.
        daten_path (str): Path to the Daten.txt file.
        processed_path (str): Path to the processed_student_register.csv file.
    """
    issues_found = False
    report_lines = []
    SIMILARITY_THRESHOLD = 2 # Max Levenshtein distance for DNI suggestions (e.g., 1 or 2 errors)

    # --- 1. Read DNIs from pln_2025.csv ---
    pln_dnis = set()
    # Store details: {dni_from_pln: {"name": "FirstName LastName", "original_pln_dni": "dni_as_in_file", "line": csv_line_num}}
    pln_dni_details = {}
    try:
        with open(pln_path, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader) # Skip header
            
            dni_col_index = -1
            header_stripped_lower = [h.strip().lower() for h in header]
            if header_stripped_lower[-1] == "dni": # Assuming DNI is the last column by default
                dni_col_index = len(header) - 1
            else:
                try: # Try to find 'dni' by name if not last
                    dni_col_index = header_stripped_lower.index("dni")
                except ValueError:
                    report_lines.append(f"ERROR: 'DNI' column not found in header of {pln_path}: {header}")
                    print("\n".join(report_lines))
                    return

            for row_num, row in enumerate(reader, 2): 
                if len(row) > dni_col_index:
                    dni = row[dni_col_index].strip() 
                    if dni: 
                        pln_dnis.add(dni)
                        name = "N/A"
                        if len(row) > 1: # Assuming Nom is col 0, Cognoms is col 1
                            name = f"{row[0].strip()} {row[1].strip()}"
                        pln_dni_details[dni] = {"name": name, "original_pln_dni": dni, "line": row_num}
                else:
                    report_lines.append(f"WARNING: Row {row_num} in {pln_path} is shorter than expected ({len(row)} cols, expected >{dni_col_index}), DNI might be missing.")
    except FileNotFoundError:
        report_lines.append(f"ERROR: File not found: {pln_path}")
        print("\n".join(report_lines))
        return
    except Exception as e:
        report_lines.append(f"ERROR: Could not read {pln_path}: {e}")
        print("\n".join(report_lines))
        return

    if not pln_dnis:
        report_lines.append(f"WARNING: No DNIs loaded from {pln_path}. Please check the file format, DNI column name, and content.")

    # --- 2. Read registration numbers from processed_student_register.csv ---
    processed_reg_dnis = set()
    processed_reg_details = {} 
    try:
        with open(processed_path, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader) 
            for row_num, row in enumerate(reader, 2):
                if row and len(row) > 0:
                    reg_dni = row[0].strip()
                    if reg_dni:
                        processed_reg_dnis.add(reg_dni)
                        name = "N/A"
                        if len(row) > 1: name = row[1].strip()
                        processed_reg_details[reg_dni] = {"name": name, "line": row_num}
    except FileNotFoundError:
        report_lines.append(f"WARNING: File not found: {processed_path}. Some consistency checks will be skipped.")
    except Exception as e:
        report_lines.append(f"ERROR: Could not read {processed_path}: {e}")

    # --- 3. Process Daten.txt ---
    try:
        with open(daten_path, mode='r', encoding='utf-8') as f:
            for line_num, line_content in enumerate(f, 1):
                parts = line_content.strip().split()
                if len(parts) < 6:
                    report_lines.append(f"WARNING: Line {line_num} in {daten_path} is too short (expected at least 6 parts): '{line_content.strip()}'")
                    continue

                scan_image_name = parts[0]
                scan_exam_id = parts[1]
                scan_dni = parts[5] 
                
                current_student_name_for_scan_dni = "Unknown (DNI not in pln_2025.csv)"

                # Check 1: DNI from Daten.txt not in pln_2025.csv (exact match)
                if scan_dni not in pln_dnis:
                    issues_found = True
                    base_issue_msg = (
                        f"ISSUE (Daten.txt line {line_num}, Image: {scan_image_name}): "
                        f"DNI '{scan_dni}' from exam scan not found in master registration list ({os.path.basename(pln_path)})."
                    )
                    report_lines.append(base_issue_msg)

                    if Levenshtein and pln_dni_details: # Suggest similar if library is available and master list is not empty
                        potential_matches = []
                        for pln_master_dni, details in pln_dni_details.items():
                            distance = Levenshtein.distance(scan_dni, pln_master_dni)
                            if 0 < distance <= SIMILARITY_THRESHOLD:
                                potential_matches.append({
                                    "dni": pln_master_dni,
                                    "name": details["name"],
                                    "distance": distance,
                                    "pln_line": details["line"]
                                })
                        
                        if potential_matches:
                            potential_matches.sort(key=lambda x: (x["distance"], x["dni"]))
                            suggestion_msg_lines = [f"  SUGGESTION for DNI '{scan_dni}': Could it be one of these from {os.path.basename(pln_path)} (max distance {SIMILARITY_THRESHOLD})?"]
                            for match in potential_matches:
                                suggestion_msg_lines.append(
                                    f"    - '{match['dni']}' (Name: {match['name']}, PLN Line: {match['pln_line']}, Distance: {match['distance']})"
                                )
                            report_lines.extend(suggestion_msg_lines)
                else: # scan_dni IS in pln_dnis (exact match found in master list)
                    current_student_name_for_scan_dni = pln_dni_details[scan_dni]["name"]
                    # original_pln_dni_format for this scan_dni is scan_dni itself, as it's a confirmed match.
                    
                    # Check 2: DNI formatting/existence issue when comparing with processed_student_register.csv
                    if processed_reg_dnis: 
                        if scan_dni not in processed_reg_dnis: # Exact string match with processed DNI
                            try:
                                int_scan_dni = int(scan_dni) 
                                found_by_int_match_in_processed = False
                                for processed_dni_str_from_set in processed_reg_dnis:
                                    try:
                                        if int(processed_dni_str_from_set) == int_scan_dni:
                                            found_by_int_match_in_processed = True
                                            issues_found = True
                                            report_lines.append(
                                                f"FORMAT ISSUE (Daten.txt line {line_num}, DNI: {scan_dni}, Matched Name: {current_student_name_for_scan_dni}): "
                                                f"DNI '{scan_dni}' (from {os.path.basename(pln_path)}) differs from "
                                                f"'{processed_dni_str_from_set}' (from {os.path.basename(processed_path)}, line {processed_reg_details.get(processed_dni_str_from_set, {}).get('line', 'N/A')}) "
                                                f"by string comparison, but matches numerically. Check for leading zeros/spaces in {os.path.basename(processed_path)}."
                                            )
                                            break 
                                    except ValueError: continue 
                                if not found_by_int_match_in_processed:
                                    issues_found = True
                                    report_lines.append(
                                        f"MATCH ISSUE (Daten.txt line {line_num}, DNI: {scan_dni}, Matched Name: {current_student_name_for_scan_dni}): "
                                        f"DNI '{scan_dni}' (from {os.path.basename(pln_path)}) "
                                        f"not found as an exact string or numeric match in {os.path.basename(processed_path)}."
                                    )
                            except ValueError: 
                                 issues_found = True
                                 report_lines.append(
                                    f"MATCH ISSUE (Daten.txt line {line_num}, DNI: {scan_dni}, Matched Name: {current_student_name_for_scan_dni}): "
                                    f"DNI '{scan_dni}' (from {os.path.basename(pln_path)}) "
                                    f"not found as an exact string match in {os.path.basename(processed_path)}. "
                                    f"The DNI '{scan_dni}' from {os.path.basename(daten_path)} is non-numeric, so numeric comparison skipped."
                                 )
                
                # Check 3 (Heuristic): Unusual Exam Sheet ID
                is_standard_id = scan_exam_id.startswith("25052700") and len(scan_exam_id) == 11 and scan_exam_id[8:].isdigit()
                is_known_problematic_pattern = scan_exam_id.startswith("250527") and \
                                               len(scan_exam_id) == 11 and \
                                               scan_exam_id[6:8] != "00"

                if not is_standard_id or is_known_problematic_pattern:
                    issues_found = True
                    report_lines.append(
                        f"EXAM ID (Daten.txt line {line_num}, Image: {scan_image_name}, DNI: {scan_dni}, Name: {current_student_name_for_scan_dni}): "
                        f"Exam Sheet ID '{scan_exam_id}' has an unusual pattern. "
                        f"Expected '25052700xxx' or similar. Please verify against exam solutions (exam.rds)."
                    )
    except FileNotFoundError:
        report_lines.append(f"ERROR: File not found: {daten_path}")
    except Exception as e:
        report_lines.append(f"ERROR: Could not read {daten_path}: {e}")

    if not issues_found and not any(r.startswith("ERROR:") or r.startswith("WARNING:") for r in report_lines):
        report_lines.append("No obvious DNI or exam ID inconsistencies found based on the defined checks.")
    elif not issues_found:
         report_lines.insert(0, "No specific data inconsistencies detected by the script, but please review any ERRORs or WARNINGs regarding file processing.")
    else:
        report_lines.insert(0, "Consistency Check Report:")

    print("\n".join(report_lines))

if __name__ == "__main__":
    pln_file = "generated/splits/pln_2025.csv"
    daten_file = "generated/splits/final_rexams_corrected/scanned_pages/Daten.txt"
    processed_file = "generated/splits/final_rexams_corrected/processed_student_register.csv"

    print(f"Checking consistency with the following files:")
    print(f"1. Master Registration: {os.path.abspath(pln_file)}")
    print(f"2. Scanned Data: {os.path.abspath(daten_file)}")
    print(f"3. Processed Registration: {os.path.abspath(processed_file)}")
    print("-" * 30)

    check_student_data_consistency(pln_file, daten_file, processed_file) 