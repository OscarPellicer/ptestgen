import random
import logging
import re

def handle_shuffle_command(args):
    """Handler for the 'shuffle' command."""
    input_md_file = args.input_md_file
    
    # --- Confirmation Prompt ---
    if not args.yes:
        confirm = input(f"This will overwrite '{input_md_file}'. Are you sure? [y/N] ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            return

    logging.info(f"Shuffling questions in-place for '{input_md_file}'...")

    try:
        with open(input_md_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logging.error(f"Input markdown file not found: {input_md_file}")
        return

    # Split the file into a header and question blocks using the '## ' delimiter
    parts = re.split(r'(?=^## )', content, flags=re.MULTILINE)
    if len(parts) < 2:
        logging.warning(f"File '{input_md_file}' does not appear to contain valid question separators ('## '). No changes made.")
        print("Warning: No questions found to shuffle.")
        return
        
    header = parts[0]
    question_blocks = parts[1:]

    # Shuffle the question blocks
    if args.seed is not None:
        random.Random(args.seed).shuffle(question_blocks)
    else:
        random.shuffle(question_blocks)

    # Reconstruct the file content
    shuffled_content = header + ''.join(question_blocks)

    try:
        with open(input_md_file, 'w', encoding='utf-8') as f:
            f.write(shuffled_content)
        logging.info(f"Successfully shuffled and overwrote '{input_md_file}'")
        print(f"Successfully shuffled {len(question_blocks)} questions in '{input_md_file}'.")
    except IOError as e:
        logging.error(f"Failed to write to file '{input_md_file}': {e}")
