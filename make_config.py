"""Interactive helper to create a custom config YAML file.

Usage:
  python3 make_config.py                  # start from scratch
  python3 make_config.py config_he.yaml   # use existing config as base
"""

import yaml
import sys
import os


def show_current(label, values):
    """Show the current/base values for a section."""
    if not values:
        return
    print(f"\n  Current {label}:")
    if isinstance(values, list):
        for v in values:
            print(f"    - {v}")
    elif isinstance(values, dict):
        for k, v in values.items():
            print(f"    {k}: {v}")


def read_lines(prompt, current=None, example=None):
    """Read multiple lines until an empty line. Returns a list of strings."""
    print(f"\n  {prompt}")
    if example and not current:
        print(f"  Example: {example}")
    print("  (paste lines, then press Enter on an empty line to finish)")
    if current:
        print("  (or just press Enter to keep current values)")
    else:
        print("  (or just press Enter to skip)")
    print()
    lines = []
    while True:
        line = input("  > ").strip()
        if not line:
            break
        lines.append(line)
    return lines if lines else None


def read_single(prompt, default=None):
    """Read a single value. Returns the value or default."""
    suffix = f" [{default}]" if default else ""
    val = input(f"\n  {prompt}{suffix}: ").strip()
    return val if val else default


def read_pairs(prompt, current=None, separator=":", example=None):
    """Read key: value pairs until an empty line. Returns a dict."""
    print(f"\n  {prompt}")
    if example and not current:
        print(f"  Example: {example}")
    print(f"  (format: key{separator} value — empty line to finish)")
    if current:
        print("  (or just press Enter to keep current values)")
    else:
        print("  (or just press Enter to skip)")
    print()
    pairs = {}
    while True:
        line = input("  > ").strip()
        if not line:
            break
        if separator in line:
            key, val = line.split(separator, 1)
            pairs[key.strip()] = val.strip()
        else:
            print(f"    Needs a '{separator}' — try again")
    return pairs if pairs else None


def read_verb_map(transaction_types, current_verbs=None):
    """Read action verbs mapped to transaction types."""
    print("\n  Action verbs: words that trigger each transaction type.")
    print("  For each type, paste verbs (one per line), then empty line for next type.")
    print("  Press Enter to keep current verbs for a type.\n")
    verbs = {}
    for tt in transaction_types:
        existing = (current_verbs or {}).get(tt, [])
        if existing:
            print(f"  --- {tt} --- (current: {', '.join(existing)})")
        else:
            print(f"  --- {tt} ---")
        lines = []
        while True:
            line = input("  > ").strip()
            if not line:
                break
            lines.append(line)
        if lines:
            verbs[tt] = lines
        elif existing:
            verbs[tt] = existing
    return verbs


def main():
    # Load base config if provided
    base = {}
    if len(sys.argv) > 1:
        base_path = sys.argv[1]
        if os.path.exists(base_path):
            with open(base_path, 'r', encoding='utf-8') as f:
                base = yaml.safe_load(f) or {}
            print(f"\n  Loaded base config: {base_path}")
        else:
            print(f"\n  Warning: {base_path} not found, starting from scratch.")

    config = {}

    print("=" * 50)
    print("  Config File Builder")
    print("=" * 50)
    print("\n  Press Enter at any step to keep base values (or skip).")
    print("  For lists, paste one item per line.\n")

    # 1. Items
    print("-" * 40)
    print("  ITEMS — your inventory product names")
    print("-" * 40)
    show_current("items", base.get('items'))
    items = read_lines("Enter item names (one per line):",
                       current=base.get('items'), example="cucumbers")
    config['items'] = items if items else base.get('items', [])

    # 2. Aliases
    print("-" * 40)
    print("  ALIASES — shortcuts for item names")
    print("-" * 40)
    base_aliases = base.get('aliases', {})
    if base_aliases:
        show_current("aliases", base_aliases)
        choice = input("\n  Keep current aliases? [Y/n/clear] ").strip().lower()
        if choice == 'clear':
            config['aliases'] = {}
        elif choice == 'n':
            aliases = read_pairs("Enter aliases:",
                                 separator=":",
                                 example="cherry tom: cherry tomatoes")
            config['aliases'] = aliases if aliases else {}
        else:
            config['aliases'] = base_aliases
    else:
        aliases = read_pairs("Enter aliases:",
                             separator=":",
                             example="cherry tom: cherry tomatoes")
        config['aliases'] = aliases if aliases else {}

    # 3. Locations
    print("-" * 40)
    print("  LOCATIONS — branch/vehicle codes")
    print("-" * 40)
    show_current("locations", base.get('locations'))
    locations = read_lines("Enter location codes (one per line):",
                           current=base.get('locations'), example="L")
    config['locations'] = locations if locations else base.get('locations', [])

    # 4. Default source
    print("-" * 40)
    print("  DEFAULT SOURCE — where stock comes from")
    print("-" * 40)
    config['default_source'] = read_single(
        "Default source name",
        default=base.get('default_source', 'warehouse'))

    # 5. Transaction types
    print("-" * 40)
    print("  TRANSACTION TYPES — categories of stock movement")
    print("-" * 40)
    base_types = base.get('transaction_types', [
        'starting_point', 'recount', 'warehouse_to_branch',
        'supplier_to_warehouse', 'eaten', 'between_branch',
        'between_warehouses', 'inside_branch',
    ])
    show_current("transaction types", base_types)
    types = read_lines("Enter transaction types:", current=base_types)
    config['transaction_types'] = types if types else base_types

    # 6. Action verbs
    print("-" * 40)
    print("  ACTION VERBS — words that trigger transaction types")
    print("-" * 40)
    base_verbs = base.get('action_verbs', {})
    if base_verbs:
        show_current("action verbs", {k: ', '.join(v) for k, v in base_verbs.items()})
    answer = input("\n  Configure action verbs? [y/N] ").strip().lower()
    if answer == 'y':
        verbs = read_verb_map(config['transaction_types'], base_verbs)
        config['action_verbs'] = verbs if verbs else base_verbs
    else:
        config['action_verbs'] = base_verbs or {
            'warehouse_to_branch': ['passed', 'gave', 'sent', 'delivered'],
            'supplier_to_warehouse': ['received', 'got'],
            'eaten': ['eaten', 'consumed', 'used'],
        }

    # 7. Unit conversions
    print("-" * 40)
    print("  UNIT CONVERSIONS — container-to-count mappings")
    print("-" * 40)
    base_conv = base.get('unit_conversions', {})
    if base_conv:
        show_current("unit conversions", {k: dict(v) for k, v in base_conv.items()})
        answer = input("\n  Configure unit conversions? [y/N/clear] ").strip().lower()
    else:
        answer = input("\n  Configure unit conversions? [y/N] ").strip().lower()
    if answer == 'clear':
        config['unit_conversions'] = {}
    elif answer == 'y':
        config['unit_conversions'] = {}
        for item in config.get('items', []):
            existing = base_conv.get(item, {})
            if existing:
                print(f"\n  --- {item} --- (current: {existing})")
            else:
                print(f"\n  --- {item} ---")
            pairs = read_pairs(
                f"Enter container conversions for '{item}':",
                current=existing,
                separator=":",
                example="box: 920",
            )
            if pairs:
                conv = {}
                for k, v in pairs.items():
                    if k == 'base_unit':
                        conv[k] = v
                    else:
                        try:
                            conv[k] = int(v)
                        except ValueError:
                            try:
                                conv[k] = float(v)
                            except ValueError:
                                conv[k] = v
                config['unit_conversions'][item] = conv
            elif existing:
                config['unit_conversions'][item] = existing
    elif base_conv:
        config['unit_conversions'] = base_conv

    # 8. Carry over remaining settings from base (parser defaults, ui, etc.)
    carry_over = [
        'prepositions', 'from_words', 'filler_words',
        'non_zero_sum_types', 'default_transfer_type', 'ui',
    ]
    for key in carry_over:
        if key in base:
            config[key] = base[key]
        elif key not in config:
            # Fallback defaults for from-scratch builds
            defaults = {
                'prepositions': {'to': ['to', 'into'], 'by': ['by'], 'from': ['from']},
                'from_words': ['from'],
                'filler_words': [
                    r"\bthat's\b", r'\bwhat\b', r'\bthe\b', r'\bof\b',
                    r'\ba\b', r'\ban\b', r'\bsome\b', r'\bvia\b',
                ],
                'non_zero_sum_types': ['eaten', 'starting_point', 'recount', 'supplier_to_warehouse'],
                'default_transfer_type': 'warehouse_to_branch',
            }
            if key in defaults:
                config[key] = defaults[key]

    # 9. Output path
    print("\n" + "=" * 50)
    default_path = 'my_config.yaml'
    out_path = read_single("Output file name", default=default_path)

    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\n  Saved to {out_path}")
    print(f"  Run with: python3 inventory_tui.py {out_path}\n")


if __name__ == '__main__':
    main()
