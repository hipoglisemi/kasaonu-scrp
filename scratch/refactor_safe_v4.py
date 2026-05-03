import os
import re

scraper_dir = "/Users/hipoglisemi/Desktop/kartavantaj-scraper/src/scrapers"

for filename in os.listdir(scraper_dir):
    if not filename.endswith(".py"): continue
    if filename in ["__init__.py", "akbank_base.py"]: continue
    
    filepath = os.path.join(scraper_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    original_content = content
    
    # 1. Fix initialization (ensure total_revived = 0 is there)
    # Look for any counter like success=0, failed=0
    init_match = re.search(r'(\s+)([a-zA-Z0-9_]+)\s*:\s*int\s*=\s*0', content)
    if not init_match:
        init_match = re.search(r'(\s+)([a-zA-Z0-9_]+)\s*=\s*0', content)
        
    if init_match and "total_revived" not in content[:content.find("for ")]:
        indent = init_match.group(1)
        # Find a good place to insert (before the first loop)
        content = content.replace(init_match.group(0), f"{init_match.group(0)}\n{indent}total_revived: int = 0")

    # 2. Fix the loop logic (elif res == "revived")
    # Find the result processing block
    res_match = re.search(r'if\s+([a-zA-Z0-9_]+)\s*==\s*["\']saved["\']:', content)
    if res_match:
        res_var = res_match.group(1)
        pattern = rf'(if\s+{res_var}\s*==\s*["\']saved["\']:\s+([a-zA-Z0-9_]+)\s*\+=\s*1)'
        if re.search(pattern, content) and f'{res_var} == "revived"' not in content:
            content = re.sub(
                pattern,
                rf'\1\n                elif {res_var} == "revived":\n                    total_revived += 1',
                content
            )

    # 3. Ensure print summary is correct
    if "total_revived" in content and "canlandı" not in content:
        content = re.sub(
            r'(atlandı,)(\s+)(\{[a-zA-Z0-9_]+\} hata aldı)',
            r'\1 {total_revived} canlandı,\2\3',
            content
        )

    # 4. Ensure log_scraper_execution has total_revived=total_revived
    if "log_scraper_execution" in content and "total_revived=total_revived" not in content:
        content = re.sub(
            r'(total_failed=([a-zA-Z0-9_]+))',
            r'\1, total_revived=total_revived',
            content
        )

    if content != original_content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Fixed: {filename}")

print("Done fixing all scrapers!")
