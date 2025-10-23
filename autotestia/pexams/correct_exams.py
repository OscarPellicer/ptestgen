import os
import logging
import csv
import uuid
import glob
from typing import Dict, List
import numpy as np

# Attempt to import OpenCV and other libraries, with graceful failure
try:
    import cv2
    import numpy as np
    from pdf2image import convert_from_path
    import easyocr
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

from . import layout

def _find_fiducial_markers(image):
    """Finds the four corner fiducial markers in the image."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    marker_contours = []
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.04 * peri, True)
        
        if len(approx) == 4:
            (x, y, w, h) = cv2.boundingRect(approx)
            aspect_ratio = w / float(h)
            
            if 0.8 <= aspect_ratio <= 1.2 and w > 20: # Relaxed aspect ratio
                marker_contours.append(approx)

    if len(marker_contours) < 4:
        return None

    # Sort contours by y-coordinate to find top and bottom pairs
    marker_contours = sorted(marker_contours, key=lambda c: cv2.boundingRect(c)[1])
    top_two = sorted(marker_contours[:2], key=lambda c: cv2.boundingRect(c)[0])
    bottom_two = sorted(marker_contours[-2:], key=lambda c: cv2.boundingRect(c)[0])
    
    tl = top_two[0]
    tr = top_two[1]
    bl = bottom_two[0]
    br = bottom_two[1]
    
    # Get the moment-based centroid for each contour for more accuracy
    def get_centroid(contour):
        M = cv2.moments(contour)
        if M["m00"] == 0: return (0, 0)
        cX = int(M["m10"] / M["m00"])
        cY = int(M["m01"] / M["m00"])
        return (cX, cY)

    return np.array([get_centroid(tl), get_centroid(tr), get_centroid(br), get_centroid(bl)], dtype="float32")

def _apply_perspective_transform(image, corners):
    """Applies a perspective transform to get a top-down view."""
    dst_width = 1800 # 180mm @ 10 pixels/mm
    dst_height = int(dst_width * (layout.PRINTABLE_HEIGHT / layout.PRINTABLE_WIDTH))

    dst = np.array([
        [0, 0], [dst_width - 1, 0],
        [dst_width - 1, dst_height - 1], [0, dst_height - 1]], dtype="float32")
        
    M = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(image, M, (dst_width, dst_height))
    return warped

def _ocr_student_id(warped_image, layout_data, px_per_mm, reader) -> str:
    """Performs OCR on the student ID boxes using easyocr."""
    gray = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY)
    
    student_id = ""
    for box in layout_data.student_id_boxes:
        tl_x, tl_y = box.top_left
        br_x, br_y = box.bottom_right
        
        x_px, y_px = int(tl_x * px_per_mm), int(tl_y * px_per_mm)
        x2_px, y2_px = int(br_x * px_per_mm), int(br_y * px_per_mm)

        # Add a small negative padding to avoid box borders
        padding = 2
        roi = gray[y_px+padding:y2_px-padding, x_px+padding:x2_px-padding]
        
        if roi.size == 0: continue

        # Use easyocr to read the digit
        result = reader.readtext(roi, allowlist='0123456789', detail=0)
        digit = result[0] if result else "?"
        student_id += digit
        
    return student_id

def _analyze_and_score(warped_image, solutions: Dict[int, int]):
    """Analyzes the warped sheet to find marked answers and scores them."""
    gray = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    h_pixels, w_pixels = thresh.shape
    px_per_mm = w_pixels / layout.PRINTABLE_WIDTH
    
    detected_answers = {}
    score = 0

    num_questions = len(solutions)
    layout_data = layout.get_answer_sheet_layout(num_questions)

    for q_num in range(1, num_questions + 1):
        if q_num not in layout_data.answer_boxes: continue

        bubbled_option = -1
        max_filled = 0

        for opt_idx in range(5):
            coords = layout_data.answer_boxes[q_num][opt_idx]
            tl_x, tl_y = coords.top_left
            br_x, br_y = coords.bottom_right
            
            x_px, y_px = int(tl_x * px_per_mm), int(tl_y * px_per_mm)
            x2_px, y2_px = int(br_x * px_per_mm), int(br_y * px_per_mm)

            roi = thresh[y_px:y2_px, x_px:x2_px]
            if roi.size == 0: continue

            filled_pixels = cv2.countNonZero(roi)
            
            if filled_pixels > max_filled and filled_pixels > (roi.size * 0.3):
                max_filled = filled_pixels
                bubbled_option = opt_idx

        detected_answers[q_num] = bubbled_option
        
        if q_num in solutions and solutions[q_num] == bubbled_option:
            score += 1
            
    return {"score": score, "total_questions": len(solutions), "answers": detected_answers}

def correct_exams(input_path: str, solutions: Dict[int, int], output_dir: str) -> bool:
    if not OPENCV_AVAILABLE:
        logging.critical("Required libraries (OpenCV, easyocr, etc.) are not installed.")
        return False

    logging.info(f"Starting pexams correction for: {input_path}")
    os.makedirs(output_dir, exist_ok=True)
    scanned_pages_dir = os.path.join(output_dir, "scanned_pages")
    os.makedirs(scanned_pages_dir, exist_ok=True)

    images_to_process: List[np.ndarray] = []

    if os.path.isdir(input_path):
        logging.info("Input path is a directory, scanning for PNG/JPG images.")
        image_files = glob.glob(os.path.join(input_path, "*.png")) + \
                      glob.glob(os.path.join(input_path, "*.jpg")) + \
                      glob.glob(os.path.join(input_path, "*.jpeg"))
        
        for image_file in image_files:
            img = cv2.imread(image_file)
            if img is not None:
                images_to_process.append(img)
            else:
                logging.warning(f"Could not read image file: {image_file}")

    elif os.path.isfile(input_path) and input_path.lower().endswith('.pdf'):
        logging.info("Input path is a PDF file, converting pages to images.")
        try:
            pil_images = convert_from_path(input_path)
            for pil_img in pil_images:
                frame = np.array(pil_img)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                images_to_process.append(frame)
        except Exception as e:
            logging.error(f"Failed to convert PDF to images: {e}")
            return False
    else:
        logging.error(f"Input path '{input_path}' is not a valid PDF file or a directory.")
        return False

    if not images_to_process:
        logging.warning("No images found to process.")
        return False

    # Initialize easyocr Reader once
    try:
        reader = easyocr.Reader(['en'])
    except Exception as e:
        logging.error(f"Failed to initialize easyocr: {e}")
        return False

    all_results = []
    layout_data_for_ocr = layout.get_answer_sheet_layout(len(solutions))

    for i, frame in enumerate(images_to_process):
        page_number = i + 1
        logging.info(f"Processing page {page_number}...")
        
        marker_corners = _find_fiducial_markers(frame)
        if marker_corners is None:
            logging.warning(f"Could not find 4 fiducial markers on page {page_number}. Skipping page.")
            continue
            
        warped_sheet = _apply_perspective_transform(frame, marker_corners)
        px_per_mm = warped_sheet.shape[1] / layout.PRINTABLE_WIDTH
        
        student_id = _ocr_student_id(warped_sheet, layout_data_for_ocr, px_per_mm, reader)
        if "?" in student_id or not student_id:
            student_id = f"unknown_{uuid.uuid4().hex[:6]}"
            logging.warning(f"Could not reliably OCR student ID for page {page_number}. Using random ID: {student_id}")

        png_path = os.path.join(scanned_pages_dir, f"{student_id}.png")
        cv2.imwrite(png_path, warped_sheet)
        logging.info(f"Saved warped scan for page {page_number} to {png_path}")

        page_result = _analyze_and_score(warped_sheet, solutions)
        page_result["page"] = page_number
        page_result["student_id"] = student_id
        
        all_results.append(page_result)

    results_csv_path = os.path.join(output_dir, "correction_results.csv")
    try:
        if not all_results:
            logging.warning("No pages were processed successfully.")
            return True

        all_q_nums = sorted(solutions.keys())
        headers = ["page", "student_id", "score", "total_questions"] + [f"answer_{q}" for q in all_q_nums]

        with open(results_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for result in all_results:
                row = {
                    "page": result.get("page", "N/A"),
                    "student_id": result.get("student_id", "N/A"),
                    "score": result.get("score", "N/A"),
                    "total_questions": result.get("total_questions", "N/A")
                }
                detected_answers = result.get("answers", {})
                for q_num in all_q_nums:
                    answer = detected_answers.get(q_num, -1)
                    row[f"answer_{q_num}"] = chr(ord('A') + answer) if answer != -1 else "NA"
                
                writer.writerow(row)
        logging.info(f"Correction complete. Results saved to: {results_csv_path}")
    except IOError as e:
        logging.error(f"Failed to write results to CSV: {e}")
        return False
    
    return True
