import re
from pathlib import Path

_CREATE_DISPLAY_NAME_RE = re.compile(
    r"""create\(\s*(?:'([^']*)'|"([^"]*)"|`([^`]*)`)\s*\).*?\.displayName\(\s*(?:'([^']*)'|"([^"]*)"|`([^`]*)`)\s*\)"""
)

for js_file in Path('work/create-stellar/instance/kubejs').rglob('*.js'):
    content = js_file.read_text('utf-8', errors='replace')
    for line in content.splitlines():
        for m in _CREATE_DISPLAY_NAME_RE.finditer(line):
            # find group 1, 2, 3
            item_id = None
            for i in range(1, 4):
                if m.group(i): item_id = m.group(i)
            if item_id and item_id.upper() in ['ABA', 'ABC', 'ACA']:
                 print(f"Found {item_id} natively inside: {js_file}")
                 print("Line:", line)
