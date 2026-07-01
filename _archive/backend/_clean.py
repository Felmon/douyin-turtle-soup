import sys, os, re
sys.stdout.reconfigure(encoding="utf-8")

SERVER_PY = "C:/Users/27871/OneDrive/Documents/抖音海龟汤/backend/server.py"
with open(SERVER_PY, "r", encoding="utf-8") as f:
    content = f.read()

# Remove the broken EMBEDDED_HTML block (everything from "# ── 嵌入式前端页面 ──" to end of the triple-quoted string)
# Find the marker
marker = "# ── 嵌入式前端页面 ──"
if marker in content:
    start = content.find(marker)
    # Find the closing triple quote
    end = content.find('"""', start + len(marker) + 20)
    if end > 0:
        # Find the end of the triple-quoted string
        # The pattern is: """ ... """
        # We need to find the closing """
        rest = content[end+3:]
        end2 = rest.find('"""')
        if end2 >= 0:
            # Remove the entire block
            block_start = content.rfind("\n\n", 0, start)  # start of the empty line before marker
            if block_start < 0:
                block_start = start
            content = content[:block_start] + content[end+3+end2+3:]
            print("Removed broken EMBEDDED_HTML block")
        else:
            print("Could not find closing triple quote")
    else:
        print("Could not find opening triple quote")
else:
    print("EMBEDDED_HTML not found, checking for alternative...")
    # Try to find by looking for 'EMBEDDED_HTML ='
    idx = content.find("EMBEDDED_HTML = ")
    if idx >= 0:
        print(f"Found EMBEDDED_HTML at {idx}")
        # Remove it
        end_of_line = content.find("\n", idx)
        # We need to find where the value ends (the closing triple quote)
        val_start = content.find('"""', idx)
        if val_start >= 0:
            val_start += 3
            val_end = content.find('"""', val_start)
            if val_end >= 0:
                val_end += 3
                content = content[:idx] + content[val_end:]
                print("EMBEDDED_HTML removed!")
            else:
                print("No closing triple quote")
        else:
            print("No opening triple quote")
    else:
        print("EMBEDDED_HTML not found at all")

with open(SERVER_PY, "w", encoding="utf-8") as f:
    f.write(content)

print("Done cleaning")
