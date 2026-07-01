import sys, os
sys.stdout.reconfigure(encoding="utf-8")

doc = open("backend/_arch_content.txt", "r", encoding="utf-8").read()

with open("docs/??????.md", "w", encoding="utf-8") as out:
    out.write(doc)

print("OK")
