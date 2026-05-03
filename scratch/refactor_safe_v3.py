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
    
    # 1. Ensure total_revived = 0 is initialized
    # Look for any of success_count, saved_count, total_saved being set to 0
    match_init = re.search(r'^(\s*)(total_saved|success_count|saved_count|saved)\s*=\s*0', content, re.MULTILINE)
    if match_init and "total_revived = 0" not in content:
        indent = match_init.group(1)
        var_name = match_init.group(2)
        content = content.replace(f"{indent}{var_name} = 0", f"{indent}{var_name} = 0\n{indent}total_revived = 0")

    # 2. Add increment logic in the loop
    res_var_match = re.search(r'([a-zA-Z0-9_]+)\s*=\s*self\._process_campaign\(url\)', content)
    if not res_var_match:
        res_var_match = re.search(r'([a-zA-Z0-9_]+)\s*=\s*self\._process_campaign\(url, db\)', content)
        
    if res_var_match:
        res_var = res_var_match.group(1)
        # Find the if/elif/else block for this variable
        # Replace the 'if res == "saved": count += 1' block
        pattern = rf'(if\s+{res_var}\s*==\s*["\']saved["\']:\s+([a-zA-Z0-9_]+)\s*\+=\s*1)'
        if re.search(pattern, content) and f'{res_var} == "revived"' not in content:
            content = re.sub(
                pattern,
                rf'\1\n                    elif {res_var} == "revived":\n                        total_revived += 1',
                content
            )

    # 3. Update summary print statement
    # Support both "Özet: ..." and "Scraping complete! ..." formats
    if "total_revived" in content and "canlandı" not in content:
        # Match Turkish summary
        content = re.sub(
            r'(atlandı,)(\s+)(\{failed_count\} hata aldı)',
            r'\1 {total_revived} canlandı,\2\3',
            content
        )
        # Match English/Generic summary
        content = re.sub(
            r'(Skipped: \{[a-zA-Z0-9_]+\})(,)(\s+)(Failed:)',
            r'\1, Revived: {total_revived}\2\3\4',
            content
        )

    # 4. Update log_scraper_execution call to include total_revived
    if "log_scraper_execution" in content and "total_revived=total_revived" not in content:
        content = re.sub(
            r'(total_failed=([a-zA-Z0-9_]+))',
            r'\1, total_revived=total_revived',
            content
        )

    if content != original_content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Refactored: {filename}")

print("Done refactoring all scrapers with correct revival logging!")
