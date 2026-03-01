import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path('libs/kubejs-string-extractor/src').resolve()))
from kubejs_string_extractor.extractor import extract_from_file

for js_file in Path('work/create-stellar/instance/kubejs').rglob('*.js'):
    try:
        res = extract_from_file(js_file)
        for s in res.strings:
            if s.value in ['ABA', 'ABC', 'BACAB']:
                print(f"File: {js_file.name}, Line {s.line_number}: {s.value}, Pattern: {s.pattern_type}")
        for key, val in res.premapped_keys.items():
            if val in ['ABA', 'ABC', 'BACAB']:
                print(f"Premapped File: {js_file.name}, {key}: {val}")
    except Exception as e:
        pass
