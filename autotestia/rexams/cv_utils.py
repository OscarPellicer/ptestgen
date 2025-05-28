import logging
import math
import os
import shutil # Added for rmtree
import sys # Added for PyPDF2 import fallback
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError # Added UnidentifiedImageError

# Imports for PDF processing (originally in correct_exams.py, now needed here)
try:
    import PyPDF2 # Maintained fork, or use 'import pypdf' for the original
except ImportError:
    try:
        import pypdf as PyPDF2 # Try the original name if the fork isn't there
        logging.info("Using 'pypdf' as PyPDF2 was not found.")
    except ImportError:
        logging.critical("PyPDF2 or pypdf library not found. Please install it: pip install PyPDF2 or pip install pypdf")
        PyPDF2 = None # To allow script to load if not strictly needed for all paths

try:
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError, PDFPopplerTimeoutError
except ImportError:
    logging.critical("pdf2image library not found. Please install it: pip install pdf2image (and ensure Poppler is installed).")
    # Define dummy exceptions if pdf2image is not found, so the function signature can be parsed
    class PDFInfoNotInstalledError(Exception):
        pass
    class PDFPageCountError(Exception):
        pass
    class PDFSyntaxError(Exception):
        pass
    class PDFPopplerTimeoutError(Exception):
        pass
    def convert_from_path(*args, **kwargs):
        return None


def find_fiducial_crosses(
    image_path: str,
    output_debug_path: Optional[str] = None,
) -> Tuple[Optional[float], Optional[np.ndarray]]:
    """
    Detects two fiducial crosses at the bottom of an image and returns the angle
    needed to make the line between them horizontal, and the processed CV image.
    Returns: Tuple (angle_degrees_of_the_line, processed_cv_image_numpy_array)
             or (None, processed_cv_image_numpy_array if processing occurred)
             or (None, None) if image loading fails.
    """
    processed_for_contours: Optional[np.ndarray] = None
    gray: Optional[np.ndarray] = None
    median_blurred: Optional[np.ndarray] = None
    thresh: Optional[np.ndarray] = None

    try:
        img = cv2.imread(image_path)
        if img is None:
            logging.error(f"Failed to load image: {image_path}")
            return None, None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # thresh = cv2.adaptiveThreshold(median_blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        #                                cv2.THRESH_BINARY_INV, blockSize=25, C=5) #Many errors
        _, processed_for_contours = cv2.threshold(gray, 97, 255, cv2.THRESH_BINARY_INV) 
        # 127 -> 7 errors, 100 -> 4, 75 -> 5, 88 -> 5, 110 -> 5, 95 -> 4, 97 -> 4
        
        if output_debug_path:
            if processed_for_contours is not None:
                cv2.imwrite(output_debug_path.replace("_crosses.png", "_final_binary_for_contours.png"), processed_for_contours)

        if processed_for_contours is None: # Should not happen if imread succeeds
            logging.error(f"Image {image_path} was loaded but no binary image was produced for contour detection.")
            return None, gray # Return gray as a last resort if available

        contours, _ = cv2.findContours(processed_for_contours, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            logging.warning(f"No contours found in {image_path} after processing steps.")
            return None, processed_for_contours

        page_height, page_width = img.shape[:2]
        candidate_cross_centroids_contours = []

        ref_min_cross_dim_px = int(3 * (300/25.4)) 
        ref_max_cross_dim_px = int(8 * (300/25.4)) 
        ref_min_area_px = (ref_min_cross_dim_px**2) * 0.3 
        ref_max_area_px = (ref_max_cross_dim_px**2) * 1.2
        
        logging.debug(f"Page dims: {page_width}x{page_height}. REF cross dim: {ref_min_cross_dim_px}-{ref_max_cross_dim_px}px. REF Area: {ref_min_area_px:.0f}-{ref_max_area_px:.0f}px^2")

        temp_candidates_for_logging = []

        for idx, c in enumerate(contours):
            x, y, w, h = cv2.boundingRect(c)
            area = cv2.contourArea(c)
            
            M = cv2.moments(c)
            if M["m00"] == 0: continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            aspect_ratio = float(w) / h if h > 0 else 0
            
            hull = cv2.convexHull(c) # Need to check for empty contour for hull
            hull_area = 0
            solidity = 0
            if hull.shape[0] >= 3 : # cv2.convexHull requires at least 3 points
                 hull_area = cv2.contourArea(hull)
                 if hull_area > 0:
                    solidity = area / float(hull_area)

            temp_candidates_for_logging.append({
                "idx": idx, "area": area, "x": x, "y": y, "w": w, "h": h, 
                "cx": cx, "cy": cy, "aspect_ratio": aspect_ratio, "solidity": solidity
            })

            # --- Very Relaxed Filters for initial candidate selection ---
            # Focus on position first: must be in the lower part of the page
            if not (page_height * 0.80 < cy < page_height * 0.99): # Relaxed lower bound for cy
                 continue
            if y < page_height * 0.75: # Relaxed top edge
                continue

            # Basic area check - very broad
            if not (ref_min_area_px * 0.2 < area < ref_max_area_px * 5.0): # Much wider area
                continue

            # Basic dimension check - very broad
            if not (ref_min_cross_dim_px * 0.2 < w < ref_max_cross_dim_px * 5.0 and \
                    ref_min_cross_dim_px * 0.2 < h < ref_max_cross_dim_px * 5.0):
                continue
            
            # Basic aspect ratio - somewhat square
            if not (0.4 < aspect_ratio < 2.5): # Relaxed aspect ratio
                continue
            
            # Solidity - can be quite low for noisy crosses
            # if not (0.3 < solidity < 1.1): # Relaxed solidity
            #    continue
            # Solidity check can be tricky if hull_area is 0 or contour is too small for hull.
            # Let's make it less strict or defer. For now, just log.

            candidate_cross_centroids_contours.append(((cx, cy), c))
        
        # Log details of all contours that passed basic positional and very lenient size/shape checks
        if output_debug_path:
            logging.debug(f"--- Potential Contours after lenient filtering for {image_path} (before pairing) ---")
            for cand_info in temp_candidates_for_logging:
                 # Check if this contour made it into candidate_cross_centroids_contours
                 # This is a bit inefficient but good for debugging this stage
                 is_selected_candidate = any(cand_info["cx"] == ccc_cx and cand_info["cy"] == ccc_cy for ((ccc_cx, ccc_cy), _) in candidate_cross_centroids_contours)
                 if is_selected_candidate: # Log only those that passed the initial lenient filters
                    logging.debug(
                        f"  Contour IDX {cand_info['idx']}: Area={cand_info['area']:.0f}, "
                        f"X={cand_info['x']}, Y={cand_info['y']}, W={cand_info['w']}, H={cand_info['h']}, "
                        f"CX={cand_info['cx']}, CY={cand_info['cy']}, "
                        f"Aspect={cand_info['aspect_ratio']:.2f}, Solidity={cand_info['solidity']:.2f} "
                        f"-> SELECTED AS CANDIDATE"
                    )
            
            debug_img_candidates = img.copy()
            for i, ((cx_cand, cy_cand), c_cand) in enumerate(candidate_cross_centroids_contours):
                 cv2.drawContours(debug_img_candidates, [c_cand], -1, (0,128,255), 1) 
                 cv2.circle(debug_img_candidates, (cx_cand, cy_cand), 3, (0,128,255), -1)
                 cv2.putText(debug_img_candidates, str(i), (cx_cand, cy_cand-10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,128,255),1)
            cv2.imwrite(output_debug_path.replace("_crosses.png", "_candidates_lenient.png"), debug_img_candidates)


        if len(candidate_cross_centroids_contours) < 2:
            logging.warning(f"Not enough candidate crosses ({len(candidate_cross_centroids_contours)}) found in {image_path} after lenient filtering to form a pair.")
            return None, processed_for_contours 

        candidate_cross_centroids_contours.sort(key=lambda item: (item[0][1], item[0][0]), reverse=True)

        found_cross_pair_details = [] 

        for i in range(len(candidate_cross_centroids_contours)):
            (cx1, cy1), c1 = candidate_cross_centroids_contours[i]
            for j in range(i + 1, len(candidate_cross_centroids_contours)):
                (cx2, cy2), c2 = candidate_cross_centroids_contours[j]

                y_diff = abs(cy1 - cy2)
                if y_diff > page_height * 0.02: 
                    continue
                
                x_diff = abs(cx1 - cx2)
                if x_diff < page_width * 0.50: 
                    continue
                
                found_cross_pair_details = [((cx1,cy1), (cx2,cy2), c1, c2)]
                logging.info(f"Found a potential pair: ({cx1},{cy1}) and ({cx2},{cy2}) with x_diff={x_diff}, y_diff={y_diff}")
                break
            if found_cross_pair_details:
                break
        
        if not found_cross_pair_details:
            logging.warning(f"Could not identify a suitable pair of fiducial crosses in {image_path} from {len(candidate_cross_centroids_contours)} candidates.")
            return None, processed_for_contours 

        (p1_centroid, p2_centroid, c1_final, c2_final) = found_cross_pair_details[0]

        if output_debug_path:
            debug_img = img.copy()
            cv2.drawContours(debug_img, [c1_final], -1, (0,255,0), 2) 
            cv2.drawContours(debug_img, [c2_final], -1, (0,255,0), 2) 
            cv2.circle(debug_img, p1_centroid, 5, (255,0,0), -1)
            cv2.circle(debug_img, p2_centroid, 5, (255,0,0), -1)
            cv2.line(debug_img, p1_centroid, p2_centroid, (255,0,0), 2)
            cv2.imwrite(output_debug_path, debug_img)

        p_left = p1_centroid if p1_centroid[0] < p2_centroid[0] else p2_centroid
        p_right = p2_centroid if p1_centroid[0] < p2_centroid[0] else p1_centroid
        
        angle_rad = math.atan2(p_right[1] - p_left[1], p_right[0] - p_left[0])
        angle_deg_of_line = - math.degrees(angle_rad) # This is the angle of the line itself.
        
        logging.info(f"Detected crosses for {image_path}. Angle of line: {angle_deg_of_line:.2f} degrees relative to horizontal.")
        return angle_deg_of_line, processed_for_contours 

    except Exception as e:
        logging.error(f"Error during cross detection for {image_path}: {e}", exc_info=True)
        if processed_for_contours is not None:
             return None, processed_for_contours
        elif gray is not None: # If processing failed but gray image exists
             _, basic_binary_fallback = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
             return None, basic_binary_fallback
        return None, None


def save_cv_image_as_pdf(
    cv_image_np: np.ndarray, 
    angle_of_line_deg: Optional[float], 
    output_pdf_path: str,
    original_pil_for_fallback_mode: Optional[str] = 'RGB' 
):
    """
    Converts an OpenCV image (NumPy array) to PIL, optionally rotates it, 
    inverts colors (black on white), and saves it as a single-page PDF.
    """
    try:
        if cv_image_np.dtype != np.uint8:
            cv_image_np = cv_image_np.astype(np.uint8) 
        
        # Invert the image: cv_image_np (thresh_cleaned) has white objects (255) on black (0)
        # We want black objects (0) on white background (255) for the PDF.
        cv_image_inverted_np = 255 - cv_image_np
        
        image_pil = Image.fromarray(cv_image_inverted_np)

        if angle_of_line_deg is not None:
            # PIL rotates counter-clockwise for positive angles.
            # To make the line horizontal, rotate by the negative of the line's angle.
            rotation_angle_for_pil = -angle_of_line_deg
            logging.debug(f"Rotating filtered image by {rotation_angle_for_pil:.2f} deg for PDF output.")
            image_pil = image_pil.rotate(rotation_angle_for_pil, resample=Image.BICUBIC, expand=True)
        
        if image_pil.mode not in ['L', 'RGB']:
            if image_pil.mode == '1': # Should not happen if input is inverted thresh_cleaned
                image_pil = image_pil.convert('L') 
            else: 
                image_pil = image_pil.convert(original_pil_for_fallback_mode or 'RGB')

        image_pil.save(output_pdf_path, "PDF", resolution=300.0, save_all=False)
        logging.info(f"Saved processed (inverted, {'rotated' if angle_of_line_deg is not None else 'unrotated'}) image to PDF: {output_pdf_path}")

    except Exception as e:
        logging.error(f"Error converting/rotating CV image or saving to PDF {output_pdf_path}: {e}", exc_info=True)
        raise 

def split_and_rotate_scans(
    all_scans_pdf_path: str,
    output_dir_for_processed_scans: str, # This should be 'output_path/scanned_pages'
    force_processing: bool = False,
    python_script_output_path: Optional[str] = None, # For creating debug image subfolder
    do_python_rotation: bool = True,
) -> Optional[str]:
    """
    Splits a multi-page PDF, attempts to rotate each page using fiducial crosses
    (if do_python_rotation is True), and saves them as individual PDFs.
    """
    if not os.path.exists(all_scans_pdf_path):
        logging.error(f"Input PDF for splitting '{all_scans_pdf_path}' not found.")
        return None

    if os.path.exists(output_dir_for_processed_scans) and not force_processing and os.listdir(output_dir_for_processed_scans):
        logging.info(f"Output directory '{output_dir_for_processed_scans}' is not empty and force is not set. Skipping Python PDF processing.")
        return output_dir_for_processed_scans
    
    if os.path.exists(output_dir_for_processed_scans) and force_processing:
        logging.info(f"Force processing: Removing existing directory {output_dir_for_processed_scans}")
        try:
            shutil.rmtree(output_dir_for_processed_scans)
        except OSError as e:
            logging.error(f"Error removing directory {output_dir_for_processed_scans}: {e}")
            return None # Cannot proceed if removal fails
    
    os.makedirs(output_dir_for_processed_scans, exist_ok=True)
    
    debug_image_dir = None
    if python_script_output_path:
        debug_image_dir = os.path.join(python_script_output_path, "python_rotation_debug_images")
        os.makedirs(debug_image_dir, exist_ok=True)
        logging.info(f"Debug images for rotation will be saved in: {debug_image_dir}")

    temp_image_storage_dir = os.path.join(output_dir_for_processed_scans, "_temp_pngs_for_rotation")
    os.makedirs(temp_image_storage_dir, exist_ok=True)

    processed_pdf_count = 0
    try:
        logging.info(f"Starting PDF splitting & rotation: {all_scans_pdf_path} -> {output_dir_for_processed_scans}")
        
        if PyPDF2 is None: # Check if PyPDF2 failed to import
            logging.error("PyPDF2 library is not available. Cannot get page count. Aborting Python PDF processing.")
            return None

        try:
            reader = PyPDF2.PdfReader(all_scans_pdf_path)
            num_pages = len(reader.pages)
            logging.info(f"PDF has {num_pages} pages.")
        except Exception as e_count:
            logging.error(f"Could not get page count using PyPDF2 for {all_scans_pdf_path}: {e_count}. Aborting Python processing.")
            return None

        for i in range(num_pages):
            page_num = i + 1
            logging.info(f"Processing page {page_num}/{num_pages}...")
            temp_png_path = os.path.join(temp_image_storage_dir, f"page_{page_num:04d}_temp.png")
            output_page_pdf_path = os.path.join(output_dir_for_processed_scans, f"page_{page_num:04d}.pdf") # Standard naming for R/exams

            try:
                page_images_pil = convert_from_path(
                    all_scans_pdf_path,
                    dpi=300,
                    first_page=page_num,
                    last_page=page_num,
                    fmt='png', # pdf2image returns PIL images
                    thread_count=1,
                )
                if not page_images_pil:
                    logging.error(f"Failed to convert page {page_num} of {all_scans_pdf_path} to image.")
                    continue
                
                current_page_pil = page_images_pil[0]
                current_page_pil.save(temp_png_path, "PNG") 

                debug_fiducial_path = None
                if debug_image_dir:
                    debug_fiducial_path = os.path.join(debug_image_dir, f"page_{page_num:04d}_fiducial_crosses.png")
                
                angle_from_fiducials, image_from_fiducial_fn = find_fiducial_crosses(
                    temp_png_path,
                    output_debug_path=debug_fiducial_path,
                )
                
                angle_for_pdf_save = None
                if do_python_rotation:
                    if angle_from_fiducials is not None:
                        angle_for_pdf_save = angle_from_fiducials
                        logging.info(f"Page {page_num}: Python rotation is ON. Using detected angle {angle_from_fiducials:.2f} deg.")
                    else:
                        logging.warning(f"Page {page_num}: Python rotation is ON, but crosses not found or angle not determined. Page will not be rotated by Python.")
                else:
                    log_msg = f"Page {page_num}: Python rotation is OFF via CLI. Page will not be rotated by Python"
                    if angle_from_fiducials is not None:
                        log_msg += f" (angle {angle_from_fiducials:.2f} deg was found but not used)."
                    logging.info(log_msg)

                if image_from_fiducial_fn is not None:
                    save_cv_image_as_pdf(
                        image_from_fiducial_fn, 
                        angle_for_pdf_save, 
                        output_page_pdf_path,
                        original_pil_for_fallback_mode=current_page_pil.mode
                    )
                else:
                    logging.warning(f"Page {page_num}: Failed to get a usable processed image from find_fiducial_crosses. Saving original (unprocessed) page orientation as PDF.")
                    fallback_pil = current_page_pil
                    if fallback_pil.mode not in ['L', 'RGB']:
                        fallback_pil = fallback_pil.convert('RGB')
                    fallback_pil.save(output_page_pdf_path, "PDF", resolution=300.0, save_all=False)
                
                processed_pdf_count += 1

            except (PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError, PDFPopplerTimeoutError) as e_pdf2img:
                 logging.error(f"pdf2image error processing page {page_num}: {e_pdf2img}. Check Poppler installation and PDF integrity.")
                 continue 
            except UnidentifiedImageError as e_pil:
                logging.error(f"Pillow UnidentifiedImageError for page {page_num} (temp PNG: {temp_png_path}): {e_pil}")
                continue
            except Exception as e_page_proc:
                logging.error(f"Unexpected error processing page {page_num}: {e_page_proc}", exc_info=True)
                continue
            finally:
                if os.path.exists(temp_png_path):
                    try:
                        os.remove(temp_png_path)
                    except OSError:
                        logging.warning(f"Could not remove temporary PNG: {temp_png_path}")
        
        if processed_pdf_count == 0 and num_pages > 0:
            logging.error("No pages were successfully processed by Python.")
            return None
        elif processed_pdf_count < num_pages:
            logging.warning(f"Successfully processed {processed_pdf_count}/{num_pages} pages.")
        else:
            logging.info(f"All {num_pages} pages processed successfully by Python.")
        
        return output_dir_for_processed_scans

    except ImportError as e_imp: 
        logging.critical(f"A required library is missing: {e_imp}. Python PDF processing cannot continue.")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during Python PDF processing: {e}", exc_info=True)
        return None
    finally:
        if os.path.exists(temp_image_storage_dir):
            try:
                shutil.rmtree(temp_image_storage_dir)
                logging.info(f"Cleaned up temporary directory: {temp_image_storage_dir}")
            except Exception as e_clean:
                logging.warning(f"Could not remove temporary image directory {temp_image_storage_dir}: {e_clean}") 