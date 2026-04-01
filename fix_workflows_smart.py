import os
import glob
import re

workflow_path = os.path.join(os.getcwd(), ".github/workflows/*.yml")

def fix_workflow_indentation(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 1. First find the correct indentation from GEMINI_API_KEY_1 or 2
    correct_indent = None
    for line in lines:
        match = re.match(r'^(\s+)GEMINI_API_KEY_[12]:', line)
        if match:
            correct_indent = match.group(1)
            break
    
    if not correct_indent:
        # Fallback to DATABASE_URL if no GEMINI keys exist yet
        for line in lines:
            match = re.match(r'^(\s+)DATABASE_URL:', line)
            if match:
                correct_indent = match.group(1)
                break
    
    if not correct_indent:
        print(f"⚠️  Skipping {os.path.basename(file_path)}: Indentation baseline not found (No GEMINI_API_KEY_1/2 or DATABASE_URL).")
        return

    # 2. Fix indentation for 3-7 to match correct_indent
    new_lines = []
    fixed_count = 0
    for line in lines:
        # Match GEMINI_API_KEY_3 to 7 with any leading space
        match = re.match(r'^\s+(GEMINI_API_KEY_[3-7]:.*)', line)
        if match:
            new_lines.append(correct_indent + match.group(1) + "\n")
            fixed_count += 1
        else:
            new_lines.append(line)
            
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    if fixed_count > 0:
        print(f"✅ Fixed {fixed_count} keys in {os.path.basename(file_path)} using {len(correct_indent)} spaces.")

if __name__ == "__main__":
    files = glob.glob(workflow_path)
    for f in files:
        fix_workflow_indentation(f)
