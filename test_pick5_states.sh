#!/bin/bash
# Test each Pick 5 state against /api/draws/recent
# Run from your project directory while Flask is running

URL="http://localhost:5001/api/draws/recent"
STATES=("Maryland" "Florida" "Virginia" "Delaware" "Ohio" "Pennsylvania" "Georgia" "Washington DC" "Louisiana")

echo "=========================================="
echo "  Pick 5 State API Test"
echo "=========================================="
echo ""

for STATE in "${STATES[@]}"; do
    RESULT=$(curl -s -X POST "$URL" \
        -H "Content-Type: application/json" \
        -d "{\"state\":\"$STATE\",\"game_type\":\"pick5\",\"start_date\":\"2026-01-01\",\"end_date\":\"2026-02-25\"}")
    
    COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
    ERROR=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',''))" 2>/dev/null)
    
    if [ -n "$ERROR" ] && [ "$ERROR" != "" ]; then
        printf "  %-20s ❌ ERROR: %s\n" "$STATE" "$ERROR"
    elif [ "$COUNT" -gt 0 ] 2>/dev/null; then
        FIRST=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['draws'][-1]['date']+' '+d['draws'][-1]['value'])" 2>/dev/null)
        LAST=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['draws'][0]['date']+' '+d['draws'][0]['value'])" 2>/dev/null)
        printf "  %-20s ✅ %4d draws  |  first: %s  last: %s\n" "$STATE" "$COUNT" "$FIRST" "$LAST"
    else
        printf "  %-20s ❌ NO DATA (HTTP response: %.80s)\n" "$STATE" "$RESULT"
    fi
done

echo ""
echo "=========================================="
