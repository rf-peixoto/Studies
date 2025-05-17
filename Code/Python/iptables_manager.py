#!/usr/bin/env python3
"""
Interactive iptables manager with Cloudflare-style DSL.
Supports:
  - Block/allow rules by IP, port, protocol
  - Pattern matching in headers or raw payload (using iptables string match)
  - Rate limiting
  - Whitelisting
  - “Under-attack” mode with timer
  - Save/load rules to JSON
  - Backup and restore of default iptables rules
"""

import os
import sys
import json
import subprocess
import threading
import time

# Configuration files
CONFIG_DIR = os.path.expanduser("~/.iptables_manager")
RULES_FILE = os.path.join(CONFIG_DIR, "rules.json")
DEFAULT_RULES_DUMP = os.path.join(CONFIG_DIR, "default_rules.v4")

# Ensure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)

def run_cmd(cmd):
    """Run shell command; exit on failure."""
    try:
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {e.cmd}\n{e.stderr.decode().strip()}")
        sys.exit(1)

def backup_default_rules():
    """Save current iptables rules for later restore."""
    with open(DEFAULT_RULES_DUMP, "w") as f:
        result = subprocess.run("iptables-save", shell=True, check=True, stdout=subprocess.PIPE)
        f.write(result.stdout.decode())
    print("Default iptables rules backed up.")

def restore_default_rules():
    """Restore iptables from backup."""
    if not os.path.exists(DEFAULT_RULES_DUMP):
        print("No default backup found.")
        return
    run_cmd(f"iptables-restore < {DEFAULT_RULES_DUMP}")
    print("iptables restored to default state.")

def load_rules():
    """Load rules JSON from disk."""
    if not os.path.exists(RULES_FILE):
        return []
    with open(RULES_FILE) as f:
        return json.load(f)

def save_rules(rules):
    """Persist rules JSON to disk."""
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=2)
    print("Rules saved.")

def build_iptables_args(rule):
    """
    Translate a rule dict into iptables command parts.
    DSL fields supported:
      - ip.src, ip.dst, tcp.sport, tcp.dport, protocol
      - payload contains <string>
      - limit rate/sec
    """
    args = []
    for cond in rule["conditions"]:
        f, op, val = cond["field"], cond["operator"], cond["value"]
        if f == "ip.src":
            args += ["-s", val]
        elif f == "ip.dst":
            args += ["-d", val]
        elif f == "protocol":
            args += ["-p", val]
        elif f == "tcp.sport":
            args += ["--sport", val]
        elif f == "tcp.dport":
            args += ["--dport", val]
        elif f in ("payload", "header"):
            # substring match; regex requires xt_regex extension
            args += ["-m", "string", "--algo", "bm", "--string", val]
        else:
            print(f"[WARN] Unsupported field: {f}")
    if rule.get("limit"):
        rate = rule["limit"].get("rate")
        args += ["-m", "limit", "--limit", rate]
    # Target
    target = "DROP" if rule["action"] == "block" else "ACCEPT"
    args += ["-j", target]
    return args

def apply_all_rules(rules):
    """Flush custom chain and reapply all rules in order."""
    # Use a dedicated chain to avoid interfering with default policy
    chain = "CFMGR"
    run_cmd(f"iptables -N {chain} || true")  # ignore if exists
    run_cmd(f"iptables -F {chain}")
    for r in rules:
        args = " ".join(build_iptables_args(r))
        run_cmd(f"iptables -A {chain} {args}")
    # Ensure new chain is hooked into INPUT
    run_cmd("iptables -C INPUT -j CFMGR || iptables -I INPUT 1 -j CFMGR")
    print("All rules applied.")

def add_rule_interactive(rules):
    """Prompt user to define a new rule."""
    name = input("Rule name: ").strip()
    action = input("Action (block/allow): ").strip()
    conds = []
    while True:
        print("Define condition (enter to finish):")
        field = input(" Field (ip.src, ip.dst, protocol, tcp.sport, tcp.dport, payload): ").strip()
        if not field:
            break
        operator = "="  # only equality or contains is supported
        val = input(" Value: ").strip()
        conds.append({"field": field, "operator": operator, "value": val})
    limit = None
    if input("Add rate limit? (y/N): ").strip().lower() == "y":
        rate = input(" Rate (e.g. 10/s): ").strip()
        limit = {"rate": rate}
    rule = {"name": name, "action": action, "conditions": conds}
    if limit:
        rule["limit"] = limit
    rules.append(rule)
    print(f"Rule '{name}' added.")
    return rules

def remove_rule_interactive(rules):
    """List and remove a rule by index."""
    if not rules:
        print("No rules to remove.")
        return rules
    for i, r in enumerate(rules, 1):
        print(f"{i}. {r['name']}")
    idx = int(input("Index to remove: "))
    removed = rules.pop(idx-1)
    print(f"Removed rule '{removed['name']}'.")
    return rules

def list_rules(rules):
    """Display all current rules."""
    if not rules:
        print("No rules defined.")
        return
    for i, r in enumerate(rules, 1):
        print(f"{i}. {r['name']} -> {r['action']}, conditions: {r['conditions']}, limit: {r.get('limit')}")

def under_attack_mode(whitelist, timeout):
    """
    Enable under-attack: block all except whitelist,
    then disable after timeout seconds.
    """
    run_cmd("iptables -F CFMGR")
    for ip in whitelist:
        run_cmd(f"iptables -A CFMGR -s {ip} -j ACCEPT")
    run_cmd(f"iptables -A CFMGR -j DROP")
    print("Under-attack mode enabled.")
    def disable():
        apply_all_rules(load_rules())
        print("Under-attack mode disabled; rules restored.")
    threading.Timer(timeout, disable).start()

def interactive_menu():
    """Main loop."""
    # On first run, back up defaults
    if not os.path.exists(DEFAULT_RULES_DUMP):
        backup_default_rules()
    rules = load_rules()
    whitelist = []
    while True:
        print("""
Interactive iptables manager — Options:
  1) List rules
  2) Add rule
  3) Remove rule
  4) Save rules
  5) Apply all rules now
  6) Restore default rules
  7) Manage whitelist
  8) Under-attack mode
  9) Exit
""")
        choice = input("Select an option: ").strip()
        if choice == "1":
            list_rules(rules)
        elif choice == "2":
            rules = add_rule_interactive(rules)
        elif choice == "3":
            rules = remove_rule_interactive(rules)
        elif choice == "4":
            save_rules(rules)
        elif choice == "5":
            apply_all_rules(rules)
        elif choice == "6":
            restore_default_rules()
        elif choice == "7":
            print("Current whitelist:", whitelist)
            ip = input("Enter IP to add (or blank to remove all): ").strip()
            if ip:
                whitelist.append(ip)
                print(f"Added {ip} to whitelist.")
            else:
                whitelist.clear()
                print("Whitelist cleared.")
        elif choice == "8":
            t = int(input("Under-attack timeout (seconds): ").strip())
            under_attack_mode(whitelist, t)
        elif choice == "9":
            print("Exiting.")
            sys.exit(0)
        else:
            print("Invalid selection, try again.")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script must be run as root.")
        sys.exit(1)
    interactive_menu()
