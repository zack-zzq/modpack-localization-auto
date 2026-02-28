
from src.modpack_localization_auto.translator import load_dictionary
from pathlib import Path
d_mini, d_patchouli = load_dictionary(Path('work/create-stellar'))
print(f'General Dict length: {len(d_mini)}')
print(f'Patchouli Dict length: {len(d_patchouli)}')
ap_translates = {k: v for k, v in d_patchouli.items() if 'advancedperipherals' in k}
print(f'Advanced Peripherals Patchouli translations count in dict: {len(ap_translates)}')

