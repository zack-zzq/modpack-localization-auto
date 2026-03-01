import sys
from pathlib import Path
sys.path.insert(0, str(Path('libs/kubejs-string-extractor/src').resolve()))
from kubejs_string_extractor.extractor import extract_from_content

content = """  event.shaped("kubejs:basic_mechanism", ["ABA", "CDC", "ABA"], {  """
res = extract_from_content(content, 'recipes.js')
for s in res.strings:
    print(s.pattern_type, repr(s.value))
