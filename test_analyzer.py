
from modpack_localization_auto.config import load_config
from modpack_localization_auto.kubejs_analyzer import analyze_kubejs_script_for_dynamic_keys
from pathlib import Path

config = load_config()
f = Path('work/create-stellar/instance/kubejs/startup_scripts/items.js')
content = f.read_text('utf-8')

res = analyze_kubejs_script_for_dynamic_keys(content, config)
from pprint import pprint
pprint(res)

