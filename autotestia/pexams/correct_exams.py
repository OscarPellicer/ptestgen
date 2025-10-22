import os
import logging
from typing import List, Tuple, Dict
import csv

# Attempt to import OpenCV and other libraries, with graceful failure
try:
    import cv2
    import numpy as np
    from pdf2image import convert_from_path
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


def _find_fiducial_markers(image):
    """
    Finds the four corner fiducial markers in the image.
    Returns the four corner points or None if not found.
    """
    # Preprocessing
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)

    # Find contours
    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    marker_contours = []
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.04 * peri, True)
        
        # Fiducial markers are squares (4 vertices)
        if len(approx) == 4:
            (x, y, w, h) = cv2.boundingRect(approx)
            aspect_ratio = w / float(h)
            
            # Check for square-like shape and a minimum size
            if 0.9 <= aspect_ratio <= 1.1 and w > 20:
                marker_contours.append(approx)

    if len(marker_contours) == 4:
        # Sort contours by their top-left corner's y-coordinate
        marker_contours = sorted(marker_contours, key=lambda c: cv2.boundingRect(c)[1])
        
        # Top two and bottom two
        top_two = sorted(marker_contours[:2], key=lambda c: cv2.boundingRect(c)[0])
        bottom_two = sorted(marker_contours[2:], key=lambda c: cv2.boundingRect(c)[0])
        
        tl = top_two[0]
        tr = top_two[1]
        bl = bottom_two[0]
        br = bottom_two[1]
        
        # Return the corner points of the markers
        return np.array([tl[0][0], tr[1][0], br[2][0], bl[3][0]], dtype="float32")
    
    return None


def _apply_perspective_transform(image, corners):
    """
    Applies a perspective transform to the image to get a top-down view.
    """
    (tl, tr, br, bl) = corners
    
    # Compute the width of the new image
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))
    
    # Compute the height of the new image
    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))
    
    # Define the destination points for the top-down view
    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")
        
    # Compute the perspective transform matrix and apply it
    M = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    
    return warped


def _analyze_and_score(warped_image, solutions: Dict[int, int], total_questions: int = 100, num_options: int = 5):
    """
    Analyzes the warped answer sheet to find marked answers and scores them.
    
    Returns a dictionary with score, total questions, and detected answers.
    """
    # Preprocess the warped image for bubble detection
    gray = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    # We assume a fixed layout for the answer grid within the warped image.
    # These values might need tuning based on the final template.
    # Let's assume the grid starts at 10% from top and left, and is 80% of width/height.
    h, w = thresh.shape
    grid_x_start = int(w * 0.1)
    grid_y_start = int(h * 0.2) # More space for header
    grid_width = int(w * 0.8)
    grid_height = int(h * 0.7)

    questions_per_col = (total_questions + 2) // 3
    col_width = grid_width // 3
    
    detected_answers = {}
    score = 0

    for q_num in range(1, total_questions + 1):
        col_index = (q_num - 1) // questions_per_col
        row_index_in_col = (q_num - 1) % questions_per_col
        
        # Calculate the y position of the question row
        row_y = grid_y_start + int(row_index_in_col * (grid_height / questions_per_col))
        
        bubbled_option = -1
        max_filled = 0

        for opt_idx in range(num_options):
            # Calculate the x position of the option bubble
            box_x = grid_x_start + (col_index * col_width) + int(opt_idx * (col_width / (num_options + 1)))
            
            # Define the ROI for the current bubble
            bubble_w = int(col_width / (num_options + 2))
            bubble_h = int(grid_height / (questions_per_col + 2))
            
            roi = thresh[row_y:row_y + bubble_h, box_x:box_x + bubble_w]
            if roi.size == 0: continue

            # Count non-zero (black) pixels
            filled_pixels = cv2.countNonZero(roi)
            
            # Simple logic: the bubble with the most black pixels is the chosen one
            # This is robust against Tipp-Ex as it makes the area white (0 non-zero pixels)
            if filled_pixels > max_filled and filled_pixels > (roi.size * 0.3): # Threshold to avoid noise
                max_filled = filled_pixels
                bubbled_option = opt_idx

        detected_answers[q_num] = bubbled_option
        
        # Score the question
        if q_num in solutions and solutions[q_num] == bubbled_option:
            score += 1
            
    return {
        "score": score,
        "total_questions": len(solutions),
        "answers": detected_answers
    }


def correct_exams(
    scanned_pdf_path: str, 
    solutions: Dict[int, int], 
    output_dir: str
) -> bool:
    """
    Corrects a scanned exam PDF containing one or more answer sheets.

    Args:
        scanned_pdf_path: Path to the PDF file with scanned answer sheets.
        solutions: A dictionary mapping question number (int) to correct option index (int, 0-based).
        output_dir: Directory to save results and debug images.

    Returns:
        True if correction was successful, False otherwise.
    """
    if not OPENCV_AVAILABLE:
        logging.critical("OpenCV, NumPy, or pdf2image is not installed. Exam correction cannot proceed.")
        logging.critical("Please install them: pip install opencv-python numpy pdf2image")
        return False

    logging.info(f"Starting pexams correction for: {scanned_pdf_path}")

    try:
        images = convert_from_path(scanned_pdf_path)
    except Exception as e:
        logging.error(f"Failed to convert PDF to images: {e}")
        return False

    all_results = []
    for i, image in enumerate(images):
        page_number = i + 1
        logging.info(f"Processing page {page_number}...")
        
        # Convert PIL Image to OpenCV format
        frame = np.array(image)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # 1. Find fiducial markers
        marker_corners = _find_fiducial_markers(frame)

        if marker_corners is None:
            logging.warning(f"Could not find 4 fiducial markers on page {page_number}. Skipping page.")
            continue
            
        # 2. Apply perspective transform
        warped_sheet = _apply_perspective_transform(frame, marker_corners)
        
        # Save debug image
        debug_image_path = os.path.join(output_dir, f"page_{page_number}_warped.png")
        cv2.imwrite(debug_image_path, warped_sheet)
        logging.info(f"Saved warped perspective debug image to {debug_image_path}")

        # 3. Analyze the warped sheet and score it
        page_result = _analyze_and_score(warped_sheet, solutions)
        page_result["page"] = page_number
        
        all_results.append(page_result)

    # Write the results to a CSV file
    results_csv_path = os.path.join(output_dir, "correction_results.csv")
    try:
        with open(results_csv_path, "w", newline="", encoding="utf-8") as f:
            # Determine headers dynamically from the first result if available
            if not all_results:
                logging.warning("No pages were processed successfully. The results CSV will be empty.")
                f.write("page,score,total_questions,status\n")
                f.write("N/A,N/A,N/A,No pages processed\n")
                return True

            # Flatten the nested 'answers' dictionary into separate columns
            # Get all possible question numbers from the solutions to create full headers
            all_q_nums = sorted(solutions.keys())
            
            headers = ["page", "score", "total_questions"]
            for q_num in all_q_nums:
                headers.append(f"answer_{q_num}")

            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for result in all_results:
                row = {
                    "page": result.get("page", "N/A"),
                    "score": result.get("score", "N/A"),
                    "total_questions": result.get("total_questions", "N/A")
                }
                # Add answers to the row, converting -1 to "NA"
                detected_answers = result.get("answers", {})
                for q_num in all_q_nums:
                    answer = detected_answers.get(q_num, -1)
                    answer_char = chr(ord('A') + answer) if answer != -1 else "NA"
                    row[f"answer_{q_num}"] = answer_char
                
                writer.writerow(row)

        logging.info(f"Correction complete. Results saved to: {results_csv_path}")

    except IOError as e:
        logging.error(f"Failed to write results to CSV file at {results_csv_path}: {e}")
        return False
    
    return True
