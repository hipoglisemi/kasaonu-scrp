import os
import re

scraper_dir = "/Users/hipoglisemi/Desktop/kartavantaj-scraper/src/scrapers"

def fix_alignment(content):
    lines = content.split('\n')
    new_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for the start of the results check
        if 'if res == "saved":' in line or 'if res == \'saved\':' in line:
            if_indent = line[:line.find('if')]
            new_lines.append(line)
            i += 1
            # Now process following lines until the end of the block
            while i < len(lines) and lines[i].strip().startswith(('elif ', 'else:', 'total_revived +=', 'success +=', 'skipped +=', 'errors +=', 'failed +=', 'success_count +=', 'skipped_count +=', 'failed_count +=')):
                curr_line = lines[i].lstrip()
                # If it's an elif/else, it should match if_indent
                if curr_line.startswith(('elif ', 'else:')):
                    new_lines.append(if_indent + curr_line)
                else:
                    # It's a body line, it should be if_indent + 4 spaces
                    new_lines.append(if_indent + "    " + curr_line)
                i += 1
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
    
    fixed = fix_alignment(content)
    
    if fixed != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(fixed)
        print(f"✅ Re-Aligned: {filename}")

print("Alignment fix complete!")
