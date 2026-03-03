#!/usr/bin/env python3
"""
Update predictions.html to combine BEFORE/AFTER sections into a prettier unified view
"""

import os
import re

template_path = os.path.expanduser('~/mylottodata-query-tool/templates/predictions.html')

# Read current file
with open(template_path, 'r') as f:
    content = f.read()

# Backup
with open(template_path + '.bak2', 'w') as f:
    f.write(content)
print("✅ Backed up to predictions.html.bak2")

# New combined section HTML
new_combined_section = '''            <div class="card">
                <h2>🎯 Combined Predictions 
                    <button onclick="copyAllNumbers()" style="float:right;padding:5px 10px;cursor:pointer;margin-left:5px;">📋 Copy All</button>
                    <button onclick="toggleView()" id="toggle-view-btn" style="float:right;padding:5px 10px;cursor:pointer;">📊 Grid View</button>
                </h2>
                <div style="display:flex;gap:20px;margin-bottom:15px;">
                    <div style="flex:1;text-align:center;padding:15px;background:linear-gradient(135deg,#1a4a2e,#2d5a3d);border-radius:8px;border:1px solid #4ecdc4;">
                        <div style="font-size:28px;font-weight:bold;color:#4ecdc4;" id="res-before-count">0</div>
                        <div style="color:#aaa;font-size:13px;">⬆️ BEFORE Seed</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:15px;background:linear-gradient(135deg,#4a2a1a,#5a3a2d);border-radius:8px;border:1px solid #ff6b6b;">
                        <div style="font-size:28px;font-weight:bold;color:#ff6b6b;" id="res-after-count">0</div>
                        <div style="color:#aaa;font-size:13px;">⬇️ AFTER Seed</div>
                    </div>
                </div>
                <div id="combined-table-view">
                    <table style="width:100%;border-collapse:collapse;">
                        <thead>
                            <tr style="background:linear-gradient(135deg,#1a4a2e,#2d5a3d);">
                                <th colspan="5" style="text-align:center;padding:12px;color:#4ecdc4;font-size:16px;border:1px solid #333;">⬆️ BEFORE Seed (Numbers that preceded the seed)</th>
                            </tr>
                            <tr style="background:#2a2a2a;">
                                <th style="padding:8px;border:1px solid #333;width:60px;">Rank</th>
                                <th style="cursor:pointer;padding:8px;border:1px solid #333;width:100px;" onclick="sortTableBefore('number')">Number ⇅</th>
                                <th style="padding:8px;border:1px solid #333;width:100px;">Norm</th>
                                <th style="cursor:pointer;padding:8px;border:1px solid #333;width:60px;" onclick="sortTableBefore('hits')">Hits ⇅</th>
                                <th style="padding:8px;border:1px solid #333;">Date Details</th>
                            </tr>
                        </thead>
                        <tbody id="res-predictions-before" style="background:#1a1a1a;"></tbody>
                        <thead>
                            <tr style="background:linear-gradient(135deg,#4a2a1a,#5a3a2d);">
                                <th colspan="5" style="text-align:center;padding:12px;color:#ff6b6b;font-size:16px;border:1px solid #333;">⬇️ AFTER Seed (Numbers that followed the seed)</th>
                            </tr>
                            <tr style="background:#2a2a2a;">
                                <th style="padding:8px;border:1px solid #333;width:60px;">Rank</th>
                                <th style="cursor:pointer;padding:8px;border:1px solid #333;width:100px;" onclick="sortTable('number')">Number ⇅</th>
                                <th style="padding:8px;border:1px solid #333;width:100px;">Norm</th>
                                <th style="cursor:pointer;padding:8px;border:1px solid #333;width:60px;" onclick="sortTable('hits')">Hits ⇅</th>
                                <th style="padding:8px;border:1px solid #333;">Date Details</th>
                            </tr>
                        </thead>
                        <tbody id="res-predictions" style="background:#1a1a1a;"></tbody>
                    </table>
                </div>
                <div id="combined-grid-view" style="display:none;">
                    <div style="margin-bottom:20px;">
                        <div style="background:linear-gradient(135deg,#1a4a2e,#2d5a3d);padding:12px;border-radius:8px 8px 0 0;text-align:center;color:#4ecdc4;font-weight:bold;font-size:15px;border:1px solid #4ecdc4;border-bottom:none;">⬆️ BEFORE Seed (<span id="res-total-count-before">0</span>)</div>
                        <div class="numbers-output" id="res-all-numbers-before" style="border-radius:0 0 8px 8px;border:1px solid #4ecdc4;border-top:none;min-height:60px;"></div>
                    </div>
                    <div>
                        <div style="background:linear-gradient(135deg,#4a2a1a,#5a3a2d);padding:12px;border-radius:8px 8px 0 0;text-align:center;color:#ff6b6b;font-weight:bold;font-size:15px;border:1px solid #ff6b6b;border-bottom:none;">⬇️ AFTER Seed (<span id="res-total-count">0</span>)</div>
                        <div class="numbers-output" id="res-all-numbers" style="border-radius:0 0 8px 8px;border:1px solid #ff6b6b;border-top:none;min-height:60px;"></div>
                    </div>
                </div>
            </div>'''

# Pattern to find the 4 cards to replace
# Card 1: Top Predictions AFTER Seed
# Card 2: All Numbers
# Card 3: Top Predictions BEFORE Seed  
# Card 4: All Numbers Before

# Find and replace each card
old_after_card = r'<div class="card">\s*<h2>Top Predictions AFTER Seed.*?</tbody></table>\s*</div>'
old_allnums_card = r'<div class="card">\s*<h2>All Numbers \(<span id="res-total-count">0</span>\)</h2>\s*<div class="numbers-output" id="res-all-numbers"></div>\s*</div>'
old_before_card = r'<div class="card">\s*<h2>Top Predictions BEFORE Seed.*?</table></div>\s*</div>'
old_allnums_before_card = r'<div class="card">\s*<h2>All Numbers Before.*?</div>\s*</div>'

# Combined pattern for all 4 cards
combined_pattern = (
    r'<div class="card">\s*<h2>Top Predictions AFTER Seed[^<]*<button[^>]*>[^<]*</button></h2>\s*'
    r'<table>.*?</tbody></table>\s*</div>\s*'
    r'<div class="card">\s*<h2>All Numbers[^<]*</h2>\s*<div[^>]*></div>\s*</div>\s*'
    r'<div class="card">\s*<h2>Top Predictions BEFORE Seed[^<]*<button[^>]*>[^<]*</button></h2>\s*'
    r'<p[^>]*>[^<]*</p>\s*<div[^>]*><table>.*?</tbody></table></div>\s*</div>\s*'
    r'<div class="card">\s*<h2>All Numbers Before[^<]*</h2>\s*<div[^>]*></div>\s*</div>'
)

new_content = re.sub(combined_pattern, new_combined_section, content, flags=re.DOTALL)

if new_content == content:
    print("❌ Complex pattern didn't match. Trying simpler approach...")
    
    # Simpler: just find line numbers and do surgical replacement
    lines = content.split('\n')
    
    # Find key markers
    after_start = None
    before_end = None
    
    for i, line in enumerate(lines):
        if 'Top Predictions AFTER Seed' in line and after_start is None:
            # Go back to find the <div class="card"> before this
            for j in range(i, max(0, i-5), -1):
                if '<div class="card">' in lines[j]:
                    after_start = j
                    break
        if 'All Numbers Before' in line:
            # Go forward to find the closing </div>
            depth = 0
            for j in range(i, min(len(lines), i+10)):
                depth += lines[j].count('<div') - lines[j].count('</div')
                if '</div>' in lines[j] and depth <= 0:
                    before_end = j
                    break
    
    if after_start and before_end:
        print(f"Found section from line {after_start} to {before_end}")
        new_lines = lines[:after_start] + [new_combined_section] + lines[before_end+1:]
        new_content = '\n'.join(new_lines)
    else:
        print(f"❌ Could not find markers. after_start={after_start}, before_end={before_end}")
        exit(1)

# Add new JavaScript functions before the closing </script> tag
new_js_functions = '''
        function toggleView() {
            const tableView = document.getElementById('combined-table-view');
            const gridView = document.getElementById('combined-grid-view');
            const btn = document.getElementById('toggle-view-btn');
            if (tableView.style.display === 'none') {
                tableView.style.display = 'block';
                gridView.style.display = 'none';
                btn.textContent = '📊 Grid View';
            } else {
                tableView.style.display = 'none';
                gridView.style.display = 'block';
                btn.textContent = '📋 Table View';
            }
        }
        
        function copyAllNumbers() {
            if (!currentResults) return;
            const beforeNums = currentResults.all_numbers_before || [];
            const afterNums = currentResults.all_numbers || [];
            const text = 'BEFORE: ' + beforeNums.join(' ') + '\\nAFTER: ' + afterNums.join(' ');
            navigator.clipboard.writeText(text).then(() => {
                alert('Copied ' + beforeNums.length + ' BEFORE + ' + afterNums.length + ' AFTER numbers!');
            });
        }
'''

# Insert before the last </script>
if new_js_functions.strip() not in new_content:
    new_content = new_content.replace('</script>\n</body>', new_js_functions + '\n    </script>\n</body>')

# Update the renderPredictions and renderPredictionsBefore to update the count displays
# Add count updates
count_update_after = "document.getElementById('res-after-count').textContent = preds.length;"
count_update_before = "document.getElementById('res-before-count').textContent = preds.length;"

# Find renderPredictions function and add count update
if count_update_after not in new_content:
    new_content = new_content.replace(
        "document.getElementById('res-predictions').innerHTML = preds.map",
        count_update_after + "\n            document.getElementById('res-predictions').innerHTML = preds.map"
    )

if count_update_before not in new_content:
    new_content = new_content.replace(
        "document.getElementById('res-predictions-before').innerHTML = preds.map",
        count_update_before + "\n            document.getElementById('res-predictions-before').innerHTML = preds.map"
    )

# Write updated file
with open(template_path, 'w') as f:
    f.write(new_content)

print("✅ Updated predictions.html with combined BEFORE/AFTER view!")
print("   - BEFORE section now appears on TOP (green theme)")
print("   - AFTER section appears on BOTTOM (red/orange theme)")
print("   - Toggle button switches between table and grid view")
print("   - Copy All button copies both lists")
print("\nRestart your app: PORT=5001 python3 app.py")
