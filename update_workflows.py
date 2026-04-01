import os
import glob

# Path to workflows
workflow_path = os.path.join(os.getcwd(), ".github/workflows/*.yml")

# Lines to add
new_keys = [
    "        GEMINI_API_KEY_3: ${{ secrets.GEMINI_API_KEY_3 }}",
    "        GEMINI_API_KEY_4: ${{ secrets.GEMINI_API_KEY_4 }}",
    "        GEMINI_API_KEY_5: ${{ secrets.GEMINI_API_KEY_5 }}",
    "        GEMINI_API_KEY_6: ${{ secrets.GEMINI_API_KEY_6 }}",
    "        GEMINI_API_KEY_7: ${{ secrets.GEMINI_API_KEY_7 }}"
]

def update_workflow(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    found_target = False
    file_modified = False
    
    for line in lines:
        new_lines.append(line)
        # We look for GEMINI_API_KEY_2 and append after it if not already present
        if "GEMINI_API_KEY_2:" in line and "GEMINI_API_KEY_3:" not in "".join(lines):
            for key_line in new_keys:
                new_lines.append(key_line + "\n")
            file_modified = True
            
    if file_modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"✅ Updated: {os.path.basename(file_path)}")
    else:
        print(f"ℹ️ Skipping (Already updated or target not found): {os.path.basename(file_path)}")

if __name__ == "__main__":
    files = glob.glob(workflow_path)
    for f in files:
        update_workflow(f)
