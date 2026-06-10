import os
import sys

# Add the project root to sys.path
sys.path.append(r'C:\Users\Oscar\ai4exams\ptestgen')

from ptestgen.artifacts import read_metadata_tsv, read_questions_md, synchronize_artifacts, write_metadata_tsv

def sync_pair(md_path, tsv_path):
    print(f'Syncing {md_path} with {tsv_path}...')
    if not os.path.exists(md_path):
        print(f'Error: {md_path} does not exist.')
        return
    if not os.path.exists(tsv_path):
        print(f'Error: {tsv_path} does not exist.')
        return
        
    records = read_metadata_tsv(tsv_path)
    md_questions = read_questions_md(md_path)
    
    updated_records = synchronize_artifacts(records, md_questions)
    write_metadata_tsv(updated_records, tsv_path)
    print(f'Finished syncing {tsv_path}')

# Define absolute paths
base_dir = r'C:\Users\Oscar\ai4exams\generated\pln\all'
pairs = [
    (os.path.join(base_dir, 'all_1.md'), os.path.join(base_dir, 'all_1.tsv')),
    (os.path.join(base_dir, 'all_1_eng.md'), os.path.join(base_dir, 'all_1_eng.tsv'))
]

for md, tsv in pairs:
    sync_pair(md, tsv)

# Verification
target_id = 'cm_97098756'
for md, tsv in pairs:
    records = read_metadata_tsv(tsv)
    found = False
    for r in records:
        if r.question_id == target_id:
            found = True
            # Based on is_question_removed in artifacts.py, let's check the status
            # We'll check both the record.status if it exists or changes_rev_to_man.status
            # From the code snippet: if record.changes_rev_to_man and record.changes_rev_to_man.status == "removed"
            status = 'unknown'
            if hasattr(r, 'changes_rev_to_man') and r.changes_rev_to_man and hasattr(r.changes_rev_to_man, 'status'):
                status = r.changes_rev_to_man.status
            
            # Also check if it's generally marked as removed in the record
            # In synchronize_artifacts, it seems to mark it.
            print(f'Question {target_id} in {os.path.basename(tsv)}: Status = {status}')
    if not found:
        print(f'Question {target_id} not found in {os.path.basename(tsv)}')



