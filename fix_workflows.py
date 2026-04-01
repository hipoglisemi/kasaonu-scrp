import os
import glob
import re

workflow_path = os.path.join(os.getcwd(), ".github/workflows/*.yml")

def fix_workflow(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        # Match lines like "        GEMINI_API_KEY_3: ..." (with 8 spaces)
        # And replace them with 10 spaces to match the env block
        if re.match(r'^        GEMINI_API_KEY_[3-7]:', line):
            new_lines.append("  " + line) # Add 2 spaces
        else:
            new_lines.append(line)
            
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"🔧 Fixed: {os.path.basename(file_path)}")

if __name__ == "__main__":
    files = glob.glob(workflow_path)
    for f in files:
        fix_workflow(f)
