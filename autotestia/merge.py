import os
import logging
from typing import List
from . import artifacts
from .schemas import QuestionRecord

def handle_merge_command(args):
    """Handler for the 'merge' command."""
    all_records = []
    seen_ids = set()

    print("Merging the following files:")
    for md_path in args.input_md_paths:
        print(f"  - '{md_path}'")
        _, tsv_path = artifacts.get_artifact_paths(md_path)
        if not os.path.exists(tsv_path):
            logging.warning(f"Corresponding TSV file not found for '{md_path}', skipping.")
            continue
        
        logging.info(f"Reading {md_path} and {tsv_path}")
        records = artifacts.read_metadata_tsv(tsv_path)
        for record in records:
            if record.question_id not in seen_ids:
                all_records.append(record)
                seen_ids.add(record.question_id)

    if not all_records:
        logging.error("No valid questions found in the input files. Merge operation cancelled.")
        return

    logging.info(f"Total unique questions after merge: {len(all_records)}")

    # Write merged artifacts
    output_md_path = args.output_md_path
    if not output_md_path.endswith('.md'):
         base_name = os.path.splitext(os.path.basename(args.input_md_paths[0]))[0]
         output_md_path = os.path.join(output_md_path, f"{base_name}_all.md")

    merged_md_path, merged_tsv_path = artifacts.get_artifact_paths(output_md_path)
    
    artifacts.write_artifacts(all_records, merged_md_path, merged_tsv_path)
    print(f"\nSuccessfully merged {len(all_records)} unique questions.")
    print(f"  -> Created merged file: '{merged_md_path}'")
