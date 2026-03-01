import sys
from pathlib import Path
sys.path.insert(0, str(Path("libs/kubejs-string-extractor/src").resolve()))
from kubejs_string_extractor.extractor import extract_from_content

f = Path('work/create-stellar/instance/kubejs/startup_scripts/items.js')
content = f.read_text('utf-8')

res = extract_from_content(content, str(f))
strings = [s.value for s in res.strings if 'echanism' in s.value]

with open('output.txt', 'w', encoding='utf-8') as out:
    out.write("Extracted mechanism strings:\n")
    for s in strings:
        out.write(repr(s) + "\n")

    d = {s: f'LOCALIZED {s}' for s in strings}

    from kubejs_string_extractor.rewriter import _build_replacer, _replace_display_name
    get_key = _build_replacer(d)

    test_line = '\t\tevent.create(`${id}_mechanism`).texture(`stellar:item/${id}_mechanism`).displayName(`Incomplete ${name} Mechanism`);'
    new_line = _replace_display_name(test_line, get_key)
    out.write('Original: ' + test_line.strip() + '\n')
    out.write('Rewritten: ' + new_line.strip() + '\n')
