import os
import re

issues = []

def check_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        try:
            content = f.read()
        except UnicodeDecodeError:
            return
            
    # Check 1: Pickle Usage
    if "import pickle" in content or "pickle." in content:
        issues.append({"severity": "CRITICAL", "file": path, "type": "Security", "desc": "Unsafe pickle deserialization risk"})

    # Check 2: Asyncio sleep block or requests in async code
    if "requests." in content and "async def " in content:
        issues.append({"severity": "HIGH", "file": path, "type": "Reliability", "desc": "Blocking requests library call inside async function"})
        
    # Check 3: Missing typing Any
    if "Any" in content and "from typing import" in content and "Any" not in content.split("from typing import")[1].split("\n")[0]:
        issues.append({"severity": "MEDIUM", "file": path, "type": "Type Issue", "desc": "Any used but missing in typing import"})
        
    # Check 4: Unused imports (basic regex check for datetime not used)
    # Actually, let's just do a manual string check.
    
    # Check 5: Memory Leak vectors (DF caching)
    if ".live_data" in content and ".append(" in content:
        issues.append({"severity": "HIGH", "file": path, "type": "Memory Leak", "desc": "Indefinite dataframe cache append"})

    # Check 6: O(N^2)
    if "for " in content and "for " in content.split("for ")[-1]:
        # Too noisy, skip
        pass

for root, _, files in os.walk('c:/Telegram-F&O-Bot/project_alpha'):
    for file in files:
        if file.endswith('.py'):
            check_file(os.path.join(root, file))
            
for file in ['c:/Telegram-F&O-Bot/bot.py', 'c:/Telegram-F&O-Bot/stratergy.py', 'c:/Telegram-F&O-Bot/notifier.py', 'c:/Telegram-F&O-Bot/broker.py', 'c:/Telegram-F&O-Bot/data_fetcher.py']:
    if os.path.exists(file):
        check_file(file)

for iss in issues:
    print(f"[{iss['severity']}] {iss['type']} -> {iss['file']}: {iss['desc']}")
