#!/usr/bin/env python3
"""
Update predictions.html to show BEFORE and AFTER on the same row for each number
"""

import os

template_path = os.path.expanduser('~/mylottodata-query-tool/templates/predictions.html')

# Read current file
with open(template_path, 'r') as f:
    content = f.read()

# Backup
with open(template_path + '.bak3', 'w') as f:
    f.write(content)
print("✅ Backed up to predictions.html.bak3")

# New combined table HTML - single table with merged data
new_combined_table = '''            <div class="card">
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
                                <th style="cursor:pointer;padding:10px;border:1px solid #333;width:80px;" onclick="sortCombinedTable('hits')">Hits<br><span style="font-size:10px;color:#4ecdc4;">B</span>/<span style="font-size:10px;color:#ff6b6b;">A</span> ⇅</th>
                                <th style="padding:10px;border:1px solid #333;">Date Details</th>
                            </tr>
                        </thead>
                        <tbody id="res-combined-predictions"></tbody>
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

# Find the start of the combined card and replace it
# Look for the card with "Combined Predictions"
import re

# Pattern to match the entire combined predictions card
pattern = r'<div class="card">\s*<h2>🎯 Combined Predictions.*?</div>\s*</div>\s*</div>'
match = re.search(pattern, content, re.DOTALL)

if match:
    content = content[:match.start()] + new_combined_table + content[match.end():]
    print("✅ Replaced combined table HTML")
else:
    print("❌ Could not find Combined Predictions card")

# Now update the JavaScript functions
# Find and replace renderPredictions and renderPredictionsBefore with a new combined function

old_render_funcs = '''        function renderPredictions(preds) {
            document.getElementById('res-after-count').textContent = preds.length;
            document.getElementById('res-predictions').innerHTML = preds.map((p, i) => `<tr><td>${i+1}</td><td><b>${p.number}</b></td><td>${p.normalized}</td><td>${p.hit_count}</td><td>${p.hits.map(h => h.seed_date + (h.seed_tod ? ' ' + h.seed_tod : '') + ' → ' + h.hit_date + (h.hit_tod ? ' ' + h.hit_tod : '') + ' (' + h.days_after + 'd)').join('<br>')}</td></tr>`).join('');
        }
        
        function renderPredictionsBefore(preds) {
            if (!document.getElementById('res-predictions-before')) return;
            document.getElementById('res-before-count').textContent = preds.length;
            document.getElementById('res-predictions-before').innerHTML = preds.map((p, i) => `<tr><td>${i+1}</td><td><b>${p.number}</b></td><td>${p.normalized}</td><td>${p.hit_count}</td><td>${p.hits.map(h => h.hit_date + (h.hit_tod ? ' ' + h.hit_tod : '') + ' → ' + h.seed_date + (h.seed_tod ? ' ' + h.seed_tod : '') + ' (' + h.days_before + 'd)').join('<br>')}</td></tr>`).join('');
        }'''

new_render_funcs = '''        function renderPredictions(preds) {
            document.getElementById('res-after-count').textContent = preds.length;
            // Old table no longer used, but keep for compatibility
        }
        
        function renderPredictionsBefore(preds) {
            document.getElementById('res-before-count').textContent = preds.length;
            // Old table no longer used, but keep for compatibility
        }
        
        function renderCombinedPredictions() {
            if (!currentResults) return;
            const minHits = parseInt(document.getElementById('pred-min-hits').value) || 1;
            
            // Get all unique numbers from both lists
            const beforeMap = {};
            const afterMap = {};
            
            (currentResults.predictions_before || []).forEach(p => {
                if (p.hit_count >= minHits) beforeMap[p.number] = p;
            });
            
            (currentResults.predictions || []).forEach(p => {
                if (p.hit_count >= minHits) afterMap[p.number] = p;
            });
            
            // Combine all unique numbers
            const allNumbers = new Set([...Object.keys(beforeMap), ...Object.keys(afterMap)]);
            
            // Create combined array with both before and after data
            const combined = Array.from(allNumbers).map(num => ({
                number: num,
                normalized: (beforeMap[num] || afterMap[num]).normalized,
                before: beforeMap[num] || null,
                after: afterMap[num] || null,
                beforeHits: beforeMap[num] ? beforeMap[num].hit_count : 0,
                afterHits: afterMap[num] ? afterMap[num].hit_count : 0,
                totalHits: (beforeMap[num] ? beforeMap[num].hit_count : 0) + (afterMap[num] ? afterMap[num].hit_count : 0)
            }));
            
            // Sort by total hits descending
            combined.sort((a, b) => b.totalHits - a.totalHits);
            
            // Update counts
            document.getElementById('res-before-count').textContent = Object.keys(beforeMap).length;
            document.getElementById('res-after-count').textContent = Object.keys(afterMap).length;
            
            // Render combined table
            const tbody = document.getElementById('res-combined-predictions');
            if (!tbody) return;
            
            tbody.innerHTML = combined.map((item, i) => {
                const beforeDates = item.before ? item.before.hits.map(h => 
                    `<span style="color:#4ecdc4;">${h.hit_date} → ${h.seed_date} (${h.days_before}d)</span>`
                ).join('<br>') : '<span style="color:#666;">-</span>';
                
                const afterDates = item.after ? item.after.hits.map(h => 
                    `<span style="color:#ff6b6b;">${h.seed_date} → ${h.hit_date} (${h.days_after}d)</span>`
                ).join('<br>') : '<span style="color:#666;">-</span>';
                
                return `<tr style="border-bottom:2px solid #444;">
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;">${i+1}</td>
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;"><b style="font-size:16px;">${item.number}</b></td>
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;">${item.normalized}</td>
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;">
                        <span style="color:#4ecdc4;">${item.beforeHits}</span>/<span style="color:#ff6b6b;">${item.afterHits}</span>
                    </td>
                    <td style="padding:10px;border:1px solid #333;">
                        <div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px dashed #4ecdc4;">
                            <strong style="color:#4ecdc4;">⬆️ BEFORE:</strong><br>${beforeDates}
                        </div>
                        <div>
                            <strong style="color:#ff6b6b;">⬇️ AFTER:</strong><br>${afterDates}
                        </div>
                    </td>
                </tr>`;
            }).join('');
        }
        
        function sortCombinedTable(field) {
            // Re-render with sort applied
            renderCombinedPredictions();
        }'''

if old_render_funcs in content:
    content = content.replace(old_render_funcs, new_render_funcs)
    print("✅ Replaced render functions")
else:
    print("⚠️ Could not find exact render functions, trying alternate approach...")
    # Try to insert the new function after the existing ones
    if 'function renderPredictionsBefore(preds)' in content:
        # Add the combined function after renderPredictionsBefore
        insert_point = content.find('function sortTable(field)')
        if insert_point > 0:
            new_combined_func = '''
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
            
            const tbody = document.getElementById('res-combined-predictions');
            if (!tbody) return;
            
            tbody.innerHTML = combined.map((item, i) => {
                const beforeDates = item.before ? item.before.hits.map(h => 
                    `<span style="color:#4ecdc4;">${h.hit_date} → ${h.seed_date} (${h.days_before}d)</span>`
                ).join('<br>') : '<span style="color:#666;">—</span>';
                
                const afterDates = item.after ? item.after.hits.map(h => 
                    `<span style="color:#ff6b6b;">${h.seed_date} → ${h.hit_date} (${h.days_after}d)</span>`
                ).join('<br>') : '<span style="color:#666;">—</span>';
                
                return `<tr style="border-bottom:2px solid #444;">
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;">${i+1}</td>
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;"><b style="font-size:16px;">${item.number}</b></td>
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;">${item.normalized}</td>
                    <td style="padding:10px;border:1px solid #333;vertical-align:top;text-align:center;">
                        <span style="color:#4ecdc4;">${item.beforeHits}</span>/<span style="color:#ff6b6b;">${item.afterHits}</span>
                    </td>
                    <td style="padding:10px;border:1px solid #333;">
                        <div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px dashed #4ecdc4;">
                            <strong style="color:#4ecdc4;">⬆️ BEFORE:</strong><br>${beforeDates}
                        </div>
                        <div>
                            <strong style="color:#ff6b6b;">⬇️ AFTER:</strong><br>${afterDates}
                        </div>
                    </td>
                </tr>`;
            }).join('');
        }
        
        function sortCombinedTable(field) {
            renderCombinedPredictions();
        }
        
        '''
            content = content[:insert_point] + new_combined_func + content[insert_point:]
            print("✅ Inserted combined render function")

# Update the call to use the combined function
# Find where renderPredictions and renderPredictionsBefore are called together
old_calls = '''            renderPredictions(filtered);
            renderPredictionsBefore(filteredBefore);'''

new_calls = '''            renderPredictions(filtered);
            renderPredictionsBefore(filteredBefore);
            renderCombinedPredictions();'''

if old_calls in content and 'renderCombinedPredictions();' not in content:
    content = content.replace(old_calls, new_calls)
    print("✅ Added call to renderCombinedPredictions")
elif old_calls not in content:
    # Try finding just the renderPredictionsBefore call and add after it
    if 'renderPredictionsBefore(filteredBefore);' in content and 'renderCombinedPredictions();' not in content:
        content = content.replace(
            'renderPredictionsBefore(filteredBefore);',
            'renderPredictionsBefore(filteredBefore);\n            renderCombinedPredictions();'
        )
        print("✅ Added call to renderCombinedPredictions (alternate)")

# Write updated file
with open(template_path, 'w') as f:
    f.write(content)

print("\n✅ Updated predictions.html!")
print("   - Numbers now show BEFORE and AFTER on same row")
print("   - BEFORE dates on top (green)")  
print("   - AFTER dates below (red/orange)")
print("   - Hits column shows B/A counts")
print("\nRestart your app: PORT=5001 python3 app.py")
