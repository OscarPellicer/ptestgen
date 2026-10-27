import os
from pathlib import Path
from typing import Tuple
import logging

# Import parsing libraries
try:
    import pypdf
except ImportError:
    pypdf = None
    logging.warning("`pypdf` library not found. Install with `pip install pypdf` to enable PDF parsing.")

try:
    import docx
except ImportError:
    docx = None
    logging.warning("`python-docx` library not found. Install with `pip install python-docx` to enable DOCX parsing.")

try:
    from pptx import Presentation
except ImportError:
    Presentation = None
    logging.warning("`python-pptx` library not found. Install with `pip install python-pptx` to enable PPTX parsing.")

try:
    from striprtf.striprtf import rtf_to_text
except ImportError:
    rtf_to_text = None
    logging.warning("`striprtf` library not found. Install with `pip install striprtf` to enable RTF parsing.")

try:
    from nbconvert import MarkdownExporter
except ImportError:
    MarkdownExporter = None
    logging.warning("`nbconvert` library not found. Install with `pip install nbconvert` to enable IPYNB parsing.")

try:
    from autocorrect import utils as pevaluate_utils
except ImportError:
    pevaluate_utils = None
    logging.warning("`pevaluate` Markdown parser not found. Falling back to legacy text extraction.")

# Formats converted to Markdown (with their images) by pevaluate's parser, when installed.
PEVALUATE_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".pdf", ".docx", ".pptx", ".html", ".htm",
    ".ipynb", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
}


def _parse_with_pevaluate(file_path: str, output_dir, markdown_config) -> Tuple[str, list]:
    """Markdown of the file and the images extracted next to it (``<stem>_assets``)."""
    asset_base_dir = Path(output_dir) if output_dir else Path(file_path).parent
    image_output_dir = asset_base_dir / f"{Path(file_path).stem}_assets"
    extraction = pevaluate_utils.read_file_markdown(
        file_path,
        image_output_dir=image_output_dir,
        image_reference_dir=asset_base_dir,
        markdown_config=markdown_config or {},
    )
    image_references = list(getattr(extraction, "image_paths", []) or [])
    logging.info(
        "Parsed %s to Markdown using pevaluate parser. Extracted %d chars and %d image asset(s).",
        file_path,
        len(extraction.markdown),
        len(image_references),
    )
    return extraction.markdown.strip(), image_references


# Legacy text extraction, one reader per format: (path) -> text.
def _read_plain_text(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def _read_pdf(file_path: str) -> str:
    reader = pypdf.PdfReader(file_path)
    return "\n".join(text for text in (page.extract_text() for page in reader.pages) if text)


def _read_docx(file_path: str) -> str:
    document = docx.Document(file_path)
    text_parts = [para.text for para in document.paragraphs if para.text]
    # Table cells are appended as separate paragraphs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    text_parts.append(cell_text)
    return "\n".join(text_parts)


def _read_pptx(file_path: str) -> str:
    text_parts = []
    for slide in Presentation(file_path).slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                shape_text = shape.text.strip()
                if shape_text:
                    text_parts.append(shape_text)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        cell_text = cell.text_frame.text.strip()
                        if cell_text:
                            text_parts.append(cell_text)
    return "\n".join(text_parts)


def _read_rtf(file_path: str) -> str:
    with open(file_path, 'r', encoding='ascii', errors='ignore') as f:  # RTF often uses extended ASCII
        return rtf_to_text(f.read())


def _read_ipynb(file_path: str) -> str:
    text_content, _resources = MarkdownExporter().from_filename(file_path)
    return text_content


# extension -> (reader, name of the module global it needs, library name, how it is described in the log)
_LEGACY_READERS = {
    ".pdf": (_read_pdf, "pypdf", "pypdf", "PDF file using pypdf"),
    ".docx": (_read_docx, "docx", "python-docx", "DOCX file using python-docx"),
    ".pptx": (_read_pptx, "Presentation", "python-pptx", "PPTX file using python-pptx"),
    ".rtf": (_read_rtf, "rtf_to_text", "striprtf", "RTF file using striprtf"),
    ".ipynb": (_read_ipynb, "MarkdownExporter", "nbconvert", "IPYNB file by converting to Markdown"),
}


def _parse_legacy(file_path: str, extension: str) -> str:
    """Plain text of the file with the format's own library ("" if it is missing or fails)."""
    if extension in (".txt", ".md"):  # Markdown is read as plain text
        text_content = _read_plain_text(file_path)
        logging.info(f"Successfully parsed {extension} file as plain text.")
        return text_content

    if extension not in _LEGACY_READERS:
        logging.warning(f"Unsupported file format: {extension} for file '{file_path}'. Cannot extract text.")
        return ""

    reader, module_global, library, description = _LEGACY_READERS[extension]
    kind = extension[1:].upper()
    if not globals()[module_global]:
        logging.warning(f"Skipping {kind} parsing for '{file_path}' as {library} library is not available.")
        return ""
    try:
        text_content = reader(file_path)
    except Exception as e:
        logging.error(f"Error parsing {kind} file '{file_path}' with {library}: {e}", exc_info=True)
        return ""
    logging.info(f"Successfully parsed {description}. Extracted {len(text_content)} characters.")
    return text_content


def parse_input_material(file_path: str, output_dir: str = None, markdown_config: dict = None) -> Tuple[str, list]:
    """
    Parses the input material file and returns its text content and the images extracted from it.

    With pevaluate installed, the supported formats are converted to Markdown and their images
    are saved under ``output_dir`` (default: the file's folder); otherwise only the text is read.

    Returns:
        Tuple[str, list]: the extracted text and the paths of the extracted images.
        Returns ("", []) if parsing fails or the format is unsupported.

    Raises:
        FileNotFoundError: If the input file does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")

    extension = os.path.splitext(file_path)[1].lower()
    logging.info(f"Attempting to parse '{file_path}' (extension: {extension})")

    if pevaluate_utils is not None and extension in PEVALUATE_EXTENSIONS:
        return _parse_with_pevaluate(file_path, output_dir, markdown_config)

    try:
        return _parse_legacy(file_path, extension).strip(), []
    except Exception as e:
        logging.error(f"An unexpected error occurred during parsing of '{file_path}': {e}", exc_info=True)
        return "", []


if __name__ == "__main__":
    import argparse
    import sys

    # Configure basic logging for the CLI tool
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description="Extract text from a document.")
    parser.add_argument("file_path", help="Path to the input document file.")

    if len(sys.argv) == 1: # No arguments provided
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    try:
        text_content, image_refs = parse_input_material(args.file_path)
        if text_content:
            print("\n--- Extracted Text ---")
            print(text_content)
        else:
            print("\nNo text content extracted or file was empty/unsupported.")

        if image_refs:
            print("\n--- Image References ---")
            for ref in image_refs:
                print(ref)
    except FileNotFoundError as e:
        logging.error(e)
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1) 

