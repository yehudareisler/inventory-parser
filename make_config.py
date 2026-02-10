"""Interactive helper to create a custom config YAML file."""

import yaml
import sys


def read_lines(prompt, example=None):
    """Read multiple lines until an empty line. Returns a list of strings."""
    print(f"\n  {prompt}")
    if example:
        print(f"  Example: {example}")
    print("  (paste lines, then press Enter on an empty line to finish)")
    print("  (or just press Enter to skip)\n")
    lines = []
    while True:
        line = input("  > ").strip()
        if not line:
            break
        lines.append(line)
    return lines


def read_single(prompt, default=None):
    """Read a single value. Returns the value or default."""
    suffix = f" [{default}]" if default else ""
    val = input(f"\n  {prompt}{suffix}: ").strip()
    return val if val else default


def read_pairs(prompt, separator=":", example=None):
    """Read key: value pairs until an empty line. Returns a dict."""
    print(f"\n  {prompt}")
    if example:
        print(f"  Example: {example}")
    print(f"  (format: key{separator} value — empty line to finish)")
    print("  (or just press Enter to skip)\n")
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
    return pairs


def read_verb_map(transaction_types):
    """Read action verbs mapped to transaction types."""
    print("\n  Action verbs: words that trigger each transaction type.")
    print("  For each type, paste verbs (one per line), then empty line for next type.")
    print("  Press Enter to skip a type.\n")
    verbs = {}
    for tt in transaction_types:
        print(f"  --- {tt} ---")
        lines = []
        while True:
            line = input("  > ").strip()
            if not line:
                break
            lines.append(line)
        if lines:
            verbs[tt] = lines
    return verbs


def main():
    config = {}

    print("=" * 50)
    print("  Config File Builder")
    print("=" * 50)
    print("\n  Press Enter at any step to skip (use defaults).")
    print("  For lists, paste one item per line.\n")

    # 1. Items
    print("-" * 40)
    print("  ITEMS — your inventory product names")
    print("-" * 40)
    items = read_lines("Enter item names (one per line):", example="cucumbers")
    if items:
        config['items'] = items

    # 2. Aliases
    print("-" * 40)
    print("  ALIASES — shortcuts for item names")
    print("-" * 40)
    aliases = read_pairs(
        "Enter aliases:",
        separator=":",
        example="cherry tom: cherry tomatoes",
    )
    if aliases:
        config['aliases'] = aliases

    # 3. Locations
    print("-" * 40)
    print("  LOCATIONS — branch/vehicle codes")
    print("-" * 40)
    locations = read_lines("Enter location codes (one per line):", example="L")
    if locations:
        config['locations'] = locations

    # 4. Default source
    print("-" * 40)
    print("  DEFAULT SOURCE — where stock comes from")
    print("-" * 40)
    default_source = read_single("Default source name", default="warehouse")
    if default_source:
        config['default_source'] = default_source

    # 5. Transaction types
    print("-" * 40)
    print("  TRANSACTION TYPES — categories of stock movement")
    print("-" * 40)
    default_types = [
        'starting_point', 'recount', 'warehouse_to_branch',
        'supplier_to_warehouse', 'eaten', 'between_branch',
        'between_warehouses', 'inside_branch',
    ]
    print(f"\n  Defaults: {', '.join(default_types)}")
    types = read_lines("Enter transaction types (or Enter to use defaults):")
    if types:
        config['transaction_types'] = types
    else:
        config['transaction_types'] = default_types

    # 6. Action verbs
    print("-" * 40)
    print("  ACTION VERBS — words that trigger transaction types")
    print("-" * 40)
    answer = input("\n  Configure action verbs? [y/N] ").strip().lower()
    if answer == 'y':
        verbs = read_verb_map(config['transaction_types'])
        if verbs:
            config['action_verbs'] = verbs
    else:
        config['action_verbs'] = {
            'warehouse_to_branch': ['passed', 'gave', 'sent', 'delivered'],
            'supplier_to_warehouse': ['received', 'got'],
            'eaten': ['eaten', 'consumed', 'used'],
        }

    # 7. Unit conversions
    print("-" * 40)
    print("  UNIT CONVERSIONS — container-to-count mappings")
    print("-" * 40)
    answer = input("\n  Configure unit conversions? [y/N] ").strip().lower()
    if answer == 'y':
        config['unit_conversions'] = {}
        for item in config.get('items', []):
            print(f"\n  --- {item} ---")
            pairs = read_pairs(
                f"Enter container conversions for '{item}':",
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

    # 8. Parser defaults
    config['prepositions'] = {'to': ['to', 'into'], 'by': ['by'], 'from': ['from']}
    config['from_words'] = ['from']
    config['filler_words'] = [
        r"\bthat's\b", r'\bwhat\b', r'\bthe\b', r'\bof\b',
        r'\ba\b', r'\ban\b', r'\bsome\b', r'\bvia\b',
    ]
    config['non_zero_sum_types'] = ['eaten', 'starting_point', 'recount', 'supplier_to_warehouse']
    config['default_transfer_type'] = 'warehouse_to_branch'

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
