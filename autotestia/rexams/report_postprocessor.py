import os
import shutil
import zipfile
import logging
import glob # To find the HTML file within student folder

# Attempt to import Playwright and set a flag
try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    # Logging will be done in functions that require Playwright if it's not available.

# Configure basic logging if this module is run standalone or not configured by caller
# This is a simple configuration. If generate_exams.py has a more complex setup,
# this might be overridden or might not be needed if imported.
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def convert_html_to_png(html_file_path: str, png_output_path: str, viewport_width: int = 1280, viewport_height: int = 800) -> bool:
    """
    Converts a single HTML file to a PNG image using Playwright.
    Assumes Playwright browsers have been installed via 'playwright install'.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logging.error("Playwright library not found or failed to import. HTML to PNG conversion skipped. Please install it: pip install playwright && playwright install")
        return False

    try:
        with sync_playwright() as p:
            browser = None
            # Try to launch a browser. Chromium is usually a good default.
            browser_types_to_try = [p.chromium, p.firefox, p.webkit]
            for browser_type in browser_types_to_try:
                try:
                    browser = browser_type.launch()
                    logging.info(f"Launched browser: {browser_type.name}")
                    break
                except PlaywrightError as e:
                    logging.warning(f"Failed to launch {browser_type.name}: {e}. Trying next available browser.")
            
            if not browser:
                logging.error("Failed to launch any Playwright browser (Chromium, Firefox, WebKit). "
                              "Ensure Playwright browsers are installed by running: playwright install")
                return False

            page = browser.new_page()
            page.set_viewport_size({"width": viewport_width, "height": viewport_height})
            
            # Convert local file path to a file URI
            html_url = f"file:///{os.path.abspath(html_file_path).replace(os.sep, '/')}"
            logging.info(f"Navigating to HTML file: {html_url}")
            
            # 'load' is generally good for local files. 'networkidle' might be too much.
            page.goto(html_url, wait_until="load") 
            
            # Ensure the output directory for the PNG exists
            os.makedirs(os.path.dirname(png_output_path), exist_ok=True)
            
            # Take a full-page screenshot
            page.screenshot(path=png_output_path, full_page=True)

            browser.close()
            logging.info(f"Successfully converted '{html_file_path}' to '{png_output_path}'")
            return True
    except PlaywrightError as e:
        logging.error(f"Playwright error during HTML to PNG conversion for '{html_file_path}': {e}")
        if "executable doesn't exist" in str(e).lower():
            logging.error("This typically means Playwright browser binaries are missing. "
                          "Please run 'playwright install' in your terminal.")
        return False
    except Exception as e:
        logging.error(f"Unexpected error during HTML to PNG conversion for '{html_file_path}': {e}", exc_info=True)
        return False

def process_exam_results_zip(exams_output_dir: str, force_regeneration: bool = False):
    """
    Unzips 'exam_corrected_results.zip' found in 'exams_output_dir',
    looks for an HTML file in each student's subfolder, and converts it to a PNG.
    The PNGs are saved in a new 'exam_corrected_results_png' directory.

    Args:
        exams_output_dir: The directory where 'exam_corrected_results.zip' is located.
        force_regeneration: If True, existing PNGs will be overwritten. 
                              If False, skips generation if the output PNG directory exists and is not empty.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logging.warning("Playwright is not available. Skipping generation of PNGs from student HTML reports.")
        return

    zip_filename = "exam_corrected_results.zip"
    zip_filepath = os.path.join(exams_output_dir, zip_filename)
    
    unzip_dir_name = "exam_corrected_results_unzipped_temp" # Temporary directory for unzipped files
    unzip_target_path = os.path.join(exams_output_dir, unzip_dir_name)
    
    png_output_dir_name = "exam_corrected_results_png"
    png_main_output_dir = os.path.join(exams_output_dir, png_output_dir_name)

    if not force_regeneration and os.path.isdir(png_main_output_dir) and os.listdir(png_main_output_dir):
        logging.info(f"PNG output directory '{png_main_output_dir}' already exists and is not empty. Skipping PNG generation. Use force option to regenerate.")
        return

    if not os.path.isfile(zip_filepath):
        logging.warning(f"'{zip_filename}' not found in '{exams_output_dir}'. Skipping PNG generation for student reports.")
        return

    logging.info(f"Starting processing of '{zip_filepath}' for student report PNG generation.")

    # Ensure a clean state for temporary and output directories
    if os.path.isdir(unzip_target_path):
        logging.info(f"Removing existing temporary unzipped directory: {unzip_target_path}")
        shutil.rmtree(unzip_target_path)
    os.makedirs(unzip_target_path, exist_ok=True)

    if os.path.isdir(png_main_output_dir):
        logging.info(f"Removing existing PNG output directory: {png_main_output_dir}")
        shutil.rmtree(png_main_output_dir)
    os.makedirs(png_main_output_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
            zip_ref.extractall(unzip_target_path)
        logging.info(f"Successfully unzipped '{zip_filename}' to '{unzip_target_path}'.")

        processed_png_count = 0
        # Iterate through items in the unzipped directory.
        # Student folders are expected to be direct children here.
        for item_name in os.listdir(unzip_target_path):
            item_full_path = os.path.join(unzip_target_path, item_name)
            
            if os.path.isdir(item_full_path):
                student_id = item_name  # Assuming folder name is the student ID
                
                # Find an HTML file (e.g., *.html or *.htm) within this student's folder.
                # This takes the first one found.
                html_files_in_student_folder = glob.glob(os.path.join(item_full_path, "*.html")) + \
                                               glob.glob(os.path.join(item_full_path, "*.htm"))
                
                if not html_files_in_student_folder:
                    logging.warning(f"No HTML file found in directory: '{item_full_path}' for student ID '{student_id}'. Skipping PNG generation for this student.")
                    continue
                
                # Use the first HTML file found.
                student_html_filepath = html_files_in_student_folder[0]
                if len(html_files_in_student_folder) > 1:
                    logging.info(f"Multiple HTML files found in '{item_full_path}'. Using: '{student_html_filepath}'.")

                png_filename = f"{student_id}.png"
                png_file_final_path = os.path.join(png_main_output_dir, png_filename)
                
                logging.info(f"Attempting to convert HTML '{student_html_filepath}' for student '{student_id}' to '{png_file_final_path}'.")
                if convert_html_to_png(student_html_filepath, png_file_final_path):
                    processed_png_count += 1
                else:
                    logging.error(f"Failed to convert HTML to PNG for student '{student_id}' from file '{student_html_filepath}'.")
        
        if processed_png_count > 0:
            logging.info(f"Successfully generated {processed_png_count} PNG student reports in '{png_main_output_dir}'.")
        else:
            # This could also mean no student folders were found or no HTMLs within them.
            logging.info(f"No student PNG reports were generated from '{zip_filename}'. Check if student folders with HTML files exist within the zip.")

    except zipfile.BadZipFile:
        logging.error(f"Error: '{zip_filepath}' is not a valid zip file or is corrupted.")
    except Exception as e:
        logging.error(f"An unexpected error occurred during the PNG generation process: {e}", exc_info=True)
    finally:
        # Clean up the temporary unzipped directory
        if os.path.isdir(unzip_target_path):
            logging.info(f"Removing temporary unzipped directory: {unzip_target_path}")
            try:
                shutil.rmtree(unzip_target_path)
            except Exception as e:
                logging.error(f"Failed to remove temporary directory {unzip_target_path}: {e}")

if __name__ == '__main__':
    # Example usage (for testing this script directly)
    print("Report Postprocessor Example Usage")
    print("This script is intended to be called by generate_exams.py")
    
    if not PLAYWRIGHT_AVAILABLE:
        print("Playwright is not installed or available. Cannot run example.")
        print("Please install it: pip install playwright && playwright install")
    else:
        print("Playwright is available.")
        # To test, you would need a dummy exams_output_dir with a
        # exam_corrected_results.zip file structured as expected.
        # e.g., dummy_output/exam_corrected_results.zip
        #       which contains student_id1/report.html, student_id2/report.html etc.
        
        # Create dummy files for testing
        test_output_dir = "temp_test_exam_output"
        os.makedirs(test_output_dir, exist_ok=True)
        
        # Create a dummy zip file
        dummy_zip_path = os.path.join(test_output_dir, "exam_corrected_results.zip")
        with zipfile.ZipFile(dummy_zip_path, 'w') as zf:
            # Create student1 folder with an HTML file
            zf.writestr("student1/report.html", "<html><body><h1>Report for Student 1</h1></body></html>")
            # Create student2 folder with an HTML file
            zf.writestr("student2/details.html", "<html><body><p>Details for Student 2.</p></body></html>")
            # Create a file at the root of the zip
            zf.writestr("processed_student_register.html", "<html><body>Overall Register</body></html>")
            # Create an empty student folder
            zf.writestr("student3/", "") # Creates a directory entry

        print(f"Created dummy zip for testing: {dummy_zip_path}")
        print(f"Running process_exam_results_zip on: {test_output_dir}")
        process_exam_results_zip(test_output_dir)
        print(f"Running again, should skip if not forced (and if PNGs were created):")
        process_exam_results_zip(test_output_dir, force_regeneration=False) 
        print(f"Running with force_regeneration=True:")
        process_exam_results_zip(test_output_dir, force_regeneration=True)
        print(f"Check the directory '{os.path.join(test_output_dir, 'exam_corrected_results_png')}' for output PNGs.")
        # Clean up dummy files after test
        # shutil.rmtree(test_output_dir) # Comment out if you want to inspect output
        print(f"Test finished. Manual cleanup of '{test_output_dir}' might be needed if you want to re-run.")
