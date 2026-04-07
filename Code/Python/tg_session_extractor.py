#!/usr/bin/env python3
"""
Extract all data from a Telethon .session file (SQLite database).
Usage: python extract_session.py <session_file>
"""

import sqlite3
import sys
import os
import json
from datetime import datetime

def print_section(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def extract_session_info(session_path):
    if not os.path.isfile(session_path):
        print(f"Error: Session file '{session_path}' not found.")
        sys.exit(1)

    # Connect to the SQLite database
    conn = sqlite3.connect(session_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Sessions table (core authentication data)
    print_section("SESSIONS TABLE")
    cursor.execute("SELECT * FROM sessions")
    sessions = cursor.fetchall()
    if sessions:
        for row in sessions:
            for key in row.keys():
                value = row[key]
                if key == 'auth_key' and value:
                    # Show only first 16 bytes as hex
                    value = value.hex()[:32] + "..." if isinstance(value, bytes) else value
                elif key == 'takeout_id':
                    pass
                print(f"  {key}: {value}")
    else:
        print("  No sessions found.")

    # 2. Entities table (cached users, chats, channels)
    print_section("ENTITIES TABLE (cached accounts & chats)")
    try:
        cursor.execute("SELECT * FROM entities")
        entities = cursor.fetchall()
        if entities:
            for row in entities:
                print(f"\n  --- Entity ---")
                for key in row.keys():
                    value = row[key]
                    if key == 'id':
                        print(f"    ID: {value}")
                    elif key == 'username':
                        print(f"    Username: @{value}" if value else "    Username: (none)")
                    elif key == 'phone':
                        print(f"    Phone: {value}" if value else "    Phone: (none)")
                    elif key == 'name':
                        print(f"    Name: {value}" if value else "    Name: (none)")
                    elif key == 'type':
                        # Decode entity type (common values)
                        type_map = {
                            0: "User",
                            1: "Chat",
                            2: "Channel",
                            3: "Chat (legacy?)"
                        }
                        print(f"    Type: {type_map.get(value, value)}")
                    elif key == 'hash':
                        print(f"    Hash: {value}")
                    elif key == 'date':
                        if value:
                            date_str = datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
                            print(f"    Cached date: {date_str}")
                        else:
                            print(f"    Cached date: (none)")
                    else:
                        print(f"    {key}: {value}")
        else:
            print("  No entities cached.")
    except sqlite3.OperationalError as e:
        print(f"  Could not read entities table: {e}")

    # 3. Update state table (for update synchronization)
    print_section("UPDATE STATE TABLE")
    try:
        cursor.execute("SELECT * FROM update_state")
        states = cursor.fetchall()
        if states:
            for row in states:
                for key in row.keys():
                    print(f"  {key}: {row[key]}")
        else:
            print("  No update state found.")
    except sqlite3.OperationalError:
        print("  Table 'update_state' does not exist.")

    # 4. Sent files table (uploaded file cache)
    print_section("SENT FILES TABLE (cached uploaded files)")
    try:
        cursor.execute("SELECT * FROM sent_files")
        files = cursor.fetchall()
        if files:
            for row in files:
                print(f"\n  --- Sent file ---")
                for key in row.keys():
                    value = row[key]
                    if key == 'md5_digest' and value:
                        value = value.hex() if isinstance(value, bytes) else value
                    print(f"    {key}: {value}")
        else:
            print("  No sent files cached.")
    except sqlite3.OperationalError:
        print("  Table 'sent_files' does not exist.")

    # 5. Version table (schema version)
    print_section("VERSION TABLE")
    try:
        cursor.execute("SELECT * FROM version")
        version = cursor.fetchone()
        if version:
            print(f"  Schema version: {version[0]}")
        else:
            print("  No version info.")
    except sqlite3.OperationalError:
        print("  Table 'version' does not exist.")

    conn.close()

def main():
    if len(sys.argv) != 2:
        print("Usage: python extract_session.py <path_to.session>")
        sys.exit(1)

    session_file = sys.argv[1]
    extract_session_info(session_file)

if __name__ == "__main__":
    main()
