#!/bin/bash
CATEGORIES=("finance" "shopping" "grocery" "travel" "technology" "driving" "health" "interior-design")
echo "{" > unsplash_pool.json

for cat in "${CATEGORIES[@]}"; do
    echo "  \"$cat\": [" >> unsplash_pool.json
    for page in 1 2 3; do
        curl -s -A "Mozilla/5.0" "https://unsplash.com/napi/search/photos?query=${cat}&per_page=20&page=${page}" \
        | grep -o '"regular":"https://images.unsplash.com/photo-[^"]*"' | cut -d'"' -f4 | sort | uniq | awk '{print "    \"" $1 "\","}' >> unsplash_pool.json
    done
    echo "  ]," >> unsplash_pool.json
done
echo "}" >> unsplash_pool.json
# clean up trailing commas using python for safety
python3 -c "import json; data=json.load(open('unsplash_pool.json', 'r').read()[:-2]+'}') rescue... wait no"
