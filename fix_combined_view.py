#!/usr/bin/env python3
"""
Clean update of predictions.html - combines BEFORE/AFTER on same row
"""

import os
import re

template_path = os.path.expanduser('~/mylottodata-query-tool/templates/predictions.html')

# Try to restore from earliest backup
for backup in ['predictions.html.bak', 'predictions.html.bak2', 'predictions.html.bak3']:
    backup_path = os.path.expanduser(f'~/mylottodata-query-tool/templates/{backup}')
    if os.path.exists(backup_path):
        print(f"Restoring from {backup}...")
        with open(backup_path, 'r') as f:
            content = f.read()
        # Check if this is a clean version (has the old separate tables)
        if 'Top Predictions AFTER Seed' in content and 'Top Predictions BEFORE Seed' in content:
            print("Found clean backup!")
            break
else:
    # No clean backup, read current
    with open(template_path, 'r') as f:
        content = f.read()

# Save new backup
with open(template_path + '.bak_clean', 'w') as f:
    f.write(content)

# New combined card HTML
new_combined_card = '''            <div class="card">
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
                            <tr style="background:#2a2a2a;">
                                <th style="padding:10px;border:1px solid #333;width:50px;">Rank</th>
                                <th style="cursor:pointer;padding:10px;border:1px solid #333;width:80px;" onclick="sortCombinedTable('number')">Number ⇅</th>
                                <th style="padding:10px;border:1px solid #333;width:80px;">Norm</th>
                                <th style="cursor:pointer;padding:10px;border:1px solid #333;width:100px;" onclick="sortCombinedTable('hits')">Hits <span style="color:#4ecdc4;">B</span>/<span style="color:#ff6b6b;">A</span> ⇅</th>
                                <th style="padding:10px;border:1px solid #333;">Date Details</th>
                            </tr>
                        </thead>
                        <tbody id="res-combined-predictions"></tbody>
                    </table>
                </div>
                <div id="combined-grid-view" style="display:none;">
                    <div style="margin-bottom:20px;">
                        <div style="background:linear-gradient(135deg,#1a4a2e,#2d5a3d);padding:12px;border-radius:8px 8px 0 0;text-align:center;color:#4ecdc4;font-weight:bold;">⬆️ BEFORE Seed (<span id="res-total-count-before">0</span>)</div>
                        <div class="numbers-output" id="res-all-numbers-before" style="border-radius:0 0 8px 8px;border:1px solid #4ecdc4;border-top:none;min-height:60px;"></div>
                    </div>
                    <div>
                        <div style="background:linear-gradient(135deg,#4a2a1a,#5a3a2d);padding:12px;border-radius:8px 8px 0 0;text-align:center;color:#ff6b6b;font-weight:bold;">⬇️ AFTER Seed (<span id="res-total-count">0</span>)</div>
                        <div class="numbers-output" id="res-all-numbers" style="border-radius:0 0 8px 8px;border:1px solid #ff6b6b;border-top:none;min-height:60px;"></div>
                    </div>
                </div>
            </div>'''

# Find and replace the 4 old cards with the new combined one
# Pattern: from "Top Predictions AFTER Seed" card through "All Numbers Before" card
lines = content.split('\n')
new_lines = []
skip_until_common = False
inserted = False

i = 0
while i < len(lines):
    line = lines[i]
    
    # Start skipping when we hit the AFTER card
    if 'Top Predictions AFTER Seed' in line and not skip_until_common:
        # Go back to find <div class="card">
        while new_lines and '<div class="card">' not in new_lines[-1]:
            new_lines.pop()
        if new_lines and '<div class="card">' in new_lines[-1]:
            new_lines.pop()  # Remove the <div class="card"> line too
        
        skip_until_common = True
        if not inserted:
            new_lines.append(new_combined_card)
            inserted = True
        i += 1
        continue
    
    # Stop skipping when we hit Common Numbers card
    if skip_until_common and 'Common Numbers' in line and 'Appear in BOTH' in line:
        # Go back to include the <div class="card" for common numbers
        # Find the card div
        j = i
        while j > 0 and '<div class="card"' not in lines[j]:
            j -= 1
        # Add from j onwards
        skip_until_common = False
        new_lines.append(lines[j])
        i = j + 1
        continue
    
    if not skip_until_common:
        new_lines.append(line)
    
    i += 1

content = '\n'.join(new_lines)

# Now add the JavaScript functions
new_js = '''
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
            navigator.clipboard.writeText(text).then(() => alert('Copied!'));
        }
        
        function renderCombinedPredictions() {
            if (!currentResults) return;
            const minHits = parseInt(document.getElementById('pred-min-hits').value) || 1;
            
            const beforeMap = {};
            const afterMap = {};
            
            (currentResults.predictions_before || []).forEach(p => {
                if (p.hit_count >= minHits) beforeMap[p.number] = p;
            });
            
            (currentResults.predictions || []).forEach(p => {
                if (p.hit_count >= minHits) afterMap[p.number] = p;
            });
            
            const allNumbers = new Set([...Object.keys(beforeMap), ...Object.keys(afterMap)]);
            
            const combined = Array.from(allNumbers).map(num => ({
                number: num,
                normalized: (beforeMap[num] || afterMap[num]).normalized,
                before: beforeMap[num] || null,
                after: afterMap[num] || null,
                beforeHits: beforeMap[num] ? beforeMap[num].hit_count : 0,
                afterHits: afterMap[num] ? afterMap[num].hit_count : 0,
                totalHits: (beforeMap[num] ? beforeMap[num].hit_count : 0) + (afterMap[num] ? afterMap[num].hit_count : 0)
            }));
            
            combined.sort((a, b) => b.totalHits - a.totalHits);
            
            document.getElementById('res-before-count').textContent = Object.keys(beforeMap).length;
            document.getElementById('res-after-count').textContent = Object.keys(afterMap).length;
            document.getElementById('res-total-count-before').textContent = (currentResults.all_numbers_before || []).length;
            document.getElementById('res-total-count').textContent = (currentResults.all_numbers || []).length;
            
            const tbody = document.getElementById('res-combined-predictions');
            if (!tbody) return;
            
            tbody.innerHTML = combined.map((item, i) => {
                const beforeDates = item.before ? item.before.hits.map(h => 
                    `<span style="color:#4ecdc4;">${h.hit_date} → ${h.seed_date} (${h.days_before}d)</span>`
                ).join('<br>') : '<span style="color:#555;">—</span>';
                
                const afterDates = item.after ? item.after.hits.map(h => 
                    `<span style="color:#ff6b6b;">${h.seed_date} → ${h.hit_date} (${h.days_after}d)</span>`
                ).join('<br>') : '<span style="color:#555;">—</span>';
                
                return `<tr style="border-bottom:1px solid #333;">
                    <td style="padding:12px;border-left:1px solid #333;vertical-align:top;text-align:center;">${i+1}</td>
                    <td style="padding:12px;vertical-align:top;text-align:center;"><b style="font-size:16px;">${item.number}</b></td>
                    <td style="padding:12px;vertical-align:top;text-align:center;color:#888;">${item.normalized}</td>
                    <td style="padding:12px;vertical-align:top;text-align:center;">
                        <span style="color:#4ecdc4;font-weight:bold;">${item.beforeHits}</span><span style="color:#666;">/</span><span style="color:#ff6b6b;font-weight:bold;">${item.afterHits}</span>
                    </td>
                    <td style="padding:12px;border-right:1px solid #333;">
                        <div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px dashed #444;">
                            <strong style="color:#4ecdc4;">⬆️ BEFORE:</strong> ${beforeDates}
                        </div>
                        <div>
                            <strong style="color:#ff6b6b;">⬇️ AFTER:</strong> ${afterDates}
                        </div>
                    </td>
                </tr>`;
            }).join('');
            
            // Also update grid view
            document.getElementById('res-all-numbers-before').innerHTML = (currentResults.all_numbers_before || []).join(' ');
            document.getElementById('res-all-numbers').innerHTML = (currentResults.all_numbers || []).join(' ');
        }
        
        function sortCombinedTable(field) {
            renderCombinedPredictions();
        }
'''

# Insert the JS functions before the last </script>
if 'function renderCombinedPredictions()' not in content:
    content = content.replace('</script>\n</body>', new_js + '\n    </script>\n</body>')
    print("✅ Added JavaScript functions")

# Update the render calls to include combined
if 'renderCombinedPredictions();' not in content:
    # Find where renderPredictions is called and add combined after
    content = re.sub(
        r'(renderPredictions\(filtered\);)\s*(renderPredictionsBefore\(filteredBefore\);)?',
        r'\1\n            renderCombinedPredictions();',
        content
    )
    print("✅ Added renderCombinedPredictions call")

# Write the file
with open(template_path, 'w') as f:
    f.write(content)

print("\n✅ Updated predictions.html!")
print("   - Single combined table with BEFORE/AFTER on same row")
print("   - BEFORE dates on top (green), AFTER below (orange)")
print("   - Toggle button for grid view")
print("\nRestart: PORT=5001 python3 app.py")
