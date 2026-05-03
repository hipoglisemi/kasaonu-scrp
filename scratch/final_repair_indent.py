import os
import re

scraper_dir = "/Users/hipoglisemi/Desktop/kartavantaj-scraper/src/scrapers"

def fix_content(content):
    # 1. Fix the double-indented elif mess (the biggest killer)
    # Search for an elif that is followed by another elif that is incorrectly indented deeper
    lines = content.split('\n')
    new_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Pattern: total_revived: int = 0 with bad leading space
        if ' total_revived:' in line and line.strip().startswith('total_revived'):
            # Correct the indentation to match the line above it
            prev_indent = ""
            if i > 0:
                prev_line = lines[i-1]
                prev_indent = prev_line[:len(prev_line) - len(prev_line.lstrip())]
            new_lines.append(f"{prev_indent}total_revived = 0")
            i += 1
            continue
            
        # Pattern: elif res == "revived" followed by nested elif res == "skipped"
        if 'elif res == "revived":' in line:
            indent = line[:line.find('elif')]
            new_lines.append(line)
            # Check next line
            if i + 1 < len(lines) and 'total_revived +=' in lines[i+1]:
                new_lines.append(lines[i+1])
                i += 2
                # Now check if the next line is the nested elif
                if i < len(lines) and 'elif res == "skipped":' in lines[i]:
                    # Fix the nested elif to be on the same level
                    nested_line = lines[i]
                    fixed_nested = indent + nested_line.lstrip()
                    new_lines.append(fixed_nested)
                    i += 1
                    continue
                continue

        new_lines.append(line)
        i += 1
        
    return '\n'.join(new_lines)

for filename in os.listdir(scraper_dir):
    if not filename.endswith(".py"): continue
    if filename in ["__init__.py", "akbank_base.py"]: continue
    
    filepath = os.path.join(scraper_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    fixed = fix_content(content)
    
    if fixed != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(fixed)
        print(f"✅ Repaired Indentation: {filename}")

print("Repair complete!")
