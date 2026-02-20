#!/usr/bin/env python3
import os

path = os.path.expanduser('~/mylottodata-query-tool/templates/predictions.html')

with open(path, 'r') as f:
    content = f.read()

# The missing functions
new_functions = '''
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
        }
        
        function sortCombinedTable(field) { renderCombinedPredictions(); }
'''

# Check if functions already exist
if 'function renderCombinedPredictions' in content:
    print("Functions already exist!")
else:
    # Insert before </script>
    content = content.replace('    </script>', new_functions + '\n    </script>')
    with open(path, 'w') as f:
        f.write(content)
    print("✅ Added missing functions!")

print("Restart: PORT=5001 python3 app.py")
