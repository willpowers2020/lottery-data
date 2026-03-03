#!/usr/bin/env python3
"""
Lottery Database Diagnostic Script
===================================
Run this on your local machine to inspect your MongoDB lottery database.

Prerequisites:
    pip install pymongo

Usage:
    python diagnose_lottery_db.py
"""

from pymongo import MongoClient
import json
from datetime import datetime

MONGO_URL = "mongodb+srv://willpowers2026:CjDDcm4xA5ZjZYHq@cluster0.nmujtyo.mongodb.net/"

def run_diagnostics():
    print("=" * 60)
    print("  LOTTERY DATABASE DIAGNOSTIC REPORT")
    print(f"  Run at: {datetime.now().isoformat()}")
    print("=" * 60)

    client = MongoClient(MONGO_URL)

    # 1. List all databases
    print("\n📦 DATABASES:")
    db_names = client.list_database_names()
    for db_name in db_names:
        print(f"  • {db_name}")

    # 2. For each non-system database, inspect collections
    for db_name in db_names:
        if db_name in ("admin", "local", "config"):
            continue
        
        db = client[db_name]
        collections = db.list_collection_names()
        
        print(f"\n{'=' * 60}")
        print(f"📂 DATABASE: {db_name}")
        print(f"   Collections: {len(collections)}")
        print(f"{'=' * 60}")

        for coll_name in collections:
            coll = db[coll_name]
            count = coll.count_documents({})
            
            print(f"\n  📋 COLLECTION: {coll_name}")
            print(f"     Documents: {count}")
            
            # Show indexes
            print(f"     Indexes:")
            for idx_name, idx_info in coll.index_information().items():
                unique = " (UNIQUE)" if idx_info.get("unique") else ""
                print(f"       - {idx_name}: {idx_info['key']}{unique}")
            
            # Show sample document
            if count > 0:
                sample = coll.find_one()
                print(f"     Sample document:")
                # Convert ObjectId etc. to string for display
                for key, value in sample.items():
                    print(f"       {key}: {repr(value)[:100]}")
                
                # Check for duplicates on common fields
                print(f"\n     Duplicate check:")
                for field in ["date", "draw_date", "drawDate", "drawNumber", "draw_number"]:
                    if field in sample:
                        pipeline = [
                            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
                            {"$match": {"count": {"$gt": 1}}},
                            {"$count": "duplicates"}
                        ]
                        result = list(coll.aggregate(pipeline))
                        dup_count = result[0]["duplicates"] if result else 0
                        print(f"       {field}: {dup_count} duplicate values found")

                # Show date range if applicable
                for field in ["date", "draw_date", "drawDate"]:
                    if field in sample:
                        try:
                            oldest = coll.find().sort(field, 1).limit(1)[0]
                            newest = coll.find().sort(field, -1).limit(1)[0]
                            print(f"\n     Date range ({field}):")
                            print(f"       Oldest: {oldest[field]}")
                            print(f"       Newest: {newest[field]}")
                        except Exception as e:
                            print(f"       Could not determine date range: {e}")
            else:
                print(f"     ⚠️  EMPTY COLLECTION")

    # 3. Summary
    print(f"\n{'=' * 60}")
    print("  DIAGNOSTIC COMPLETE")
    print(f"{'=' * 60}")
    print("\nCopy and paste this entire output and share it with Claude!")

    client.close()

if __name__ == "__main__":
    run_diagnostics()
