#!/usr/bin/env python3
"""
Fix all DC hyphenated pattern gaps in app.py's get_games_for_prediction()

DC games in the rebuilt DB use hyphenated names: DC-2, DC-3, DC-4, DC-5
Current patterns:
  pick2: has 'dc 2', 'dc2' but MISSING 'dc-2'  ← FIX
  pick3: has 'dc-3' ✅
  pick4: has 'dc-4' ✅  
  pick5: has 'dc-5' (after your sed fix) ✅

Run: python fix_dc_patterns.py
"""

import re

def fix():
    with open('app.py', 'r') as f:
        content = f.read()
    
    changes = 0
    
    # Fix pick2: add 'dc-2' 
    old = "'dc 2', 'dc2', 'cash 2'"
    new = "'dc 2', 'dc2', 'dc-2', 'cash 2'"
    if 'dc-2' not in content.split('pick2')[1][:200]:
        content = content.replace(old, new)
        changes += 1
        print("✅ Added 'dc-2' to pick2 patterns")
    else:
        print("⏭️  pick2 already has 'dc-2'")
    
    # Verify pick5 has dc-5 (from your earlier sed fix)
    pick5_section = content[content.find("'pick5':"):content.find("'fantasy5':")]
    if 'dc-5' in pick5_section:
        print("✅ pick5 already has 'dc-5'")
    else:
        print("⚠️  pick5 still missing 'dc-5' — adding it")
        content = content.replace("'dc 5', 'dc5',", "'dc 5', 'dc5', 'dc-5',")
        changes += 1
    
    if changes:
        with open('app.py', 'w') as f:
            f.write(content)
        print(f"\n✅ Applied {changes} fix(es) to app.py")
    else:
        print("\n✅ All patterns already correct")


if __name__ == '__main__':
    fix()
