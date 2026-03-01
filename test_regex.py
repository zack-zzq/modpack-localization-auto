import re

pattern1 = re.compile(r"""\.displayName\(\s*(?:'([^']*)'|"([^"]*)"|`([^`]*)`)\s*\)""")
line = 'event.create(`${id}_mechanism`).texture(`stellar:item/incomplete_${id}_mechanism`).displayName(`Incomplete ${name} Mechanism`);'

m1 = pattern1.search(line)
if m1:
    print("DISPLAY MATCHED:", m1.groups())
else:
    print("DISPLAY NO MATCH")

pattern2 = re.compile(
    r"""create\(\s*(?:'([^']*)'|"([^"]*)"|`([^`]*)`)\s*\).*?\.displayName\(\s*(?:'([^']*)'|"([^"]*)"|`([^`]*)`)\s*\)"""
)
m2 = pattern2.search(line)
if m2:
    print("CREATE MATCHED:", m2.groups())
else:
    print("CREATE NO MATCH")
