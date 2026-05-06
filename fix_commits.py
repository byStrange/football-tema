import re, sys, pathlib

TARGETS = """
core/services/game.py
core/services/player.py
core/services/payment.py
core/services/debt.py
bot/handlers/group.py
bot/middleware.py
bot/utils.py
notifications/live_message.py
payment/screenshot.py
""".strip().splitlines()

pat = re.compile(r'^[ \t]*await uow\.commit\(\)[ \t]*\n', re.MULTILINE)

for rel in TARGETS:
    p = pathlib.Path(rel)
    if not p.exists():
        print("SKIP", rel)
        continue
    txt = p.read_text()
    new = pat.sub('', txt)
    if new != txt:
        p.write_text(new)
        print("FIXED", rel)
    else:
        print("OK   ", rel)
