"""Inventory message parser.

Parses messy WhatsApp-style messages into structured inventory transactions.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import get_close_matches


# ============================================================
# Public API
# ============================================================


def fuzzy_resolve(text, candidates, aliases=None, cutoff=0.6):
    """Resolve text against candidates + optional aliases.

    Returns (canonical_name, match_type) where match_type is
    'exact', 'alias', 'fuzzy', or (None, None) if no match.
    """
    text_lower = text.strip().lower()
    if not text_lower:
        return None, None

    # 1. Exact match against candidates
    for c in candidates:
        if c.lower() == text_lower:
            return c, 'exact'

    # 2. Exact alias match
    if aliases:
        for a, target in aliases.items():
            if a.lower() == text_lower:
                return target, 'alias'

    # 3. Fuzzy match against candidates + alias keys
    all_targets = [c.lower() for c in candidates]
    if aliases:
        all_targets.extend(a.lower() for a in aliases)
    short_cutoff = max(cutoff, 0.8) if len(text_lower) <= 4 else cutoff
    matches = get_close_matches(text_lower, all_targets, n=1, cutoff=short_cutoff)
    if matches:
        match = matches[0]
        # Resolve back to canonical
        if aliases:
            for a, target in aliases.items():
                if a.lower() == match:
                    return target, 'fuzzy'
        for c in candidates:
            if c.lower() == match:
                return c, 'fuzzy'

    return None, None

@dataclass
class ParseResult:
    rows: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    unparseable: list = field(default_factory=list)


def parse(text, config, today=None):
    if today is None:
        today = date.today()

    text = _strip_metadata(text)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    parsed = [_parse_line(line, config) for line in lines]
    merged = _merge_lines(parsed, config)
    _broadcast_context(merged)
    return _generate_result(merged, config, today)


# ============================================================
# Preprocessing
# ============================================================

_METADATA_PATTERNS = [
    re.compile(r'<This message was edited>', re.IGNORECASE),
    re.compile(r'<Media omitted>', re.IGNORECASE),
]


def _strip_metadata(text):
    for pattern in _METADATA_PATTERNS:
        text = pattern.sub('', text)
    return text.strip()


# ============================================================
# Line parsing
# ============================================================

def _parse_line(text, config):
    r = {
        'raw': text,
        'qty': None, 'item': None, 'item_raw': None,
        'container': None, 'trans_type': None,
        'location': None, 'direction': None,
        'date': None, 'notes_extra': None,
        'has_qty': False, 'has_item': False,
    }

    remaining = text

    # Strip leading +/-
    remaining = re.sub(r'^\s*[+\-]\s*', '', remaining).strip()

    # Special pattern: "took X out of Y [item]"
    took = re.match(r'took\s+(\d+)\s+out\s+of\s+(\d+)\s+(.+)', remaining, re.IGNORECASE)
    if took:
        r['qty'] = int(took.group(1))
        r['has_qty'] = True
        r['notes_extra'] = f'had {took.group(2)} total'
        item, raw = _match_item(took.group(3).strip(), config)
        if item:
            r['item'], r['item_raw'], r['has_item'] = item, raw, True
        return r

    # Extract date
    date_val, remaining = _extract_date(remaining)
    if date_val:
        r['date'] = date_val

    # Extract location with direction
    loc, direction, remaining = _extract_location(remaining, config)
    if loc:
        r['location'], r['direction'] = loc, direction

    # Extract action verb
    trans_type, remaining = _extract_verb(remaining, config)
    if trans_type:
        r['trans_type'] = trans_type

    # Extract supplier info ("from [name]") if relevant
    from_words = config.get('from_words', ['from'])
    if any(w in remaining.lower() for w in [fw.lower() for fw in from_words]):
        supplier, remaining = _extract_supplier_info(remaining, config)
        if supplier:
            r['notes_extra'] = f'from {supplier}'

    # Extract quantity + container
    remaining_before_qty = remaining
    qty, container, remaining = _extract_qty(remaining, config)
    if qty is not None:
        r['qty'], r['has_qty'] = qty, True
    if container:
        r['container'] = container

    # Clean up remaining text and match item
    remaining = _remove_filler(remaining, config)
    if remaining.strip():
        item, raw = _match_item(remaining, config)
        if item:
            r['item'], r['item_raw'], r['has_item'] = item, raw, True
        else:
            r['_unmatched_text'] = remaining.strip()

    # Multi-number disambiguation: if item wasn't found, try other numbers as qty
    if not r['has_item'] and r['has_qty']:
        all_numbers = re.findall(r'\b(\d+)\b', remaining_before_qty)
        if len(all_numbers) > 1:
            for num_str in all_numbers:
                if int(num_str) == r['qty']:
                    continue
                trial_qty = int(num_str)
                trial_text = remaining_before_qty.replace(num_str, '', 1).strip()
                trial_text = _remove_filler(trial_text, config)
                trial_cont, trial_after = _extract_container(trial_text, config)
                trial_item, trial_raw = _match_item(
                    trial_after if trial_cont else trial_text, config)
                if trial_item:
                    r['qty'], r['has_qty'] = trial_qty, True
                    r['item'], r['item_raw'], r['has_item'] = trial_item, trial_raw, True
                    r.pop('_unmatched_text', None)
                    if trial_cont:
                        r['container'] = trial_cont
                    break

    # Apply container conversion if we have item + container + qty
    if r['item'] and r['container'] and r['qty'] is not None:
        converted = _convert_container(r['item'], r['container'], r['qty'], config)
        if converted is not None:
            r['qty'] = converted
            r['container'] = None

    return r


# ============================================================
# Extraction helpers
# ============================================================

def _extract_date(text):
    # DD.M.YY or DD.MM.YYYY
    m = re.search(r'\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b', text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        remaining = (text[:m.start()] + text[m.end():]).strip()
        try:
            return date(year, month, day), remaining
        except ValueError:
            pass
    # M/DD/YY
    m = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b', text)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        remaining = (text[:m.start()] + text[m.end():]).strip()
        try:
            return date(year, month, day), remaining
        except ValueError:
            pass
    # DDMMYY (6 digits, no separators)
    m = re.search(r'\b(\d{6})\b', text)
    if m:
        s = m.group(1)
        day, month, year = int(s[:2]), int(s[2:4]), int(s[4:6]) + 2000
        remaining = (text[:m.start()] + text[m.end():]).strip()
        try:
            return date(year, month, day), remaining
        except ValueError:
            pass
    return None, text


def _extract_location(text, config):
    locations = config.get('locations', [])
    default_source = config.get('default_source', 'warehouse')
    all_locs = locations + ([default_source] if default_source not in locations else [])

    # Expand with location aliases (aliases whose target is a known location)
    aliases = config.get('aliases', {})
    loc_set = {l.lower() for l in all_locs}
    loc_alias_map = {}
    for alias_key, alias_target in aliases.items():
        if alias_target in all_locs or alias_target.lower() in loc_set:
            loc_alias_map[alias_key] = alias_target
            if alias_key not in all_locs:
                all_locs.append(alias_key)

    # Configurable prepositions: {direction: [words]}
    prep_config = config.get('prepositions', {
        'to': ['to', 'into'],
        'by': ['by'],
        'from': ['from'],
    })

    for loc in sorted(all_locs, key=len, reverse=True):
        for direction, preps in prep_config.items():
            for prep in sorted(preps, key=len, reverse=True):
                # For short/non-ASCII prepositions (e.g., Hebrew ל, ב):
                # require word boundary before prep and separator between prep and loc
                if len(prep) <= 2 and not prep.isascii():
                    pattern = rf'(?:^|\s){re.escape(prep)}[\-\s]*{re.escape(loc)}(?=\s|$)'
                else:
                    pattern = rf'\b{re.escape(prep)}\s+(?:the\s+)?{re.escape(loc)}\b'
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    # Strip any leading whitespace captured by lookaround
                    start = m.start()
                    if start < len(text) and text[start].isspace():
                        start += 1
                    remaining = (text[:start] + text[m.end():]).strip()
                    canonical = loc_alias_map.get(loc, loc)
                    return canonical, direction, remaining
    # Fuzzy fallback for multi-char location names
    # Use higher cutoff — location false positives consume words from text
    multi_char_locs = [l for l in all_locs if len(l) > 2]
    if multi_char_locs:
        words = text.split()
        for i, word in enumerate(words):
            w = word.strip()
            if not w or len(w) <= 2:
                continue
            cutoff = 0.85 if len(w) <= 4 else 0.75
            matches = get_close_matches(w.lower(),
                                        [l.lower() for l in multi_char_locs],
                                        n=1, cutoff=cutoff)
            if matches:
                # Resolve back to canonical
                for loc in multi_char_locs:
                    if loc.lower() == matches[0]:
                        canonical = loc_alias_map.get(loc, loc)
                        remaining = ' '.join(words[:i] + words[i+1:]).strip()
                        return canonical, 'to', remaining
                        break

    return None, None, text


def _extract_verb(text, config):
    for trans_type, verbs in config.get('action_verbs', {}).items():
        for verb in sorted(verbs, key=len, reverse=True):
            pattern = rf'\b{re.escape(verb)}\b'
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                remaining = (text[:m.start()] + text[m.end():]).strip()
                return trans_type, remaining

    # Match transaction type names directly (longest first)
    # Also match dash/space variants (e.g. "warehouse-to-branch" matches "warehouse_to_branch")
    aliases = config.get('aliases', {})
    for tt in sorted(config.get('transaction_types', []), key=len, reverse=True):
        # Build pattern that treats underscores, dashes, and spaces as interchangeable
        tt_pattern = re.escape(tt).replace('_', r'[\s_-]')
        if len(tt) <= 2 and not tt.isascii():
            pattern = rf'(?:^|(?<=\s)){tt_pattern}(?=\s|$)'
        else:
            pattern = rf'(?:^|(?<=\s)|(?<=\b)){tt_pattern}(?=\s|$|\b)'
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            remaining = (text[:m.start()] + text[m.end():]).strip()
            return tt, remaining

    # Match aliases that point to a transaction type
    tt_set = {t.lower() for t in config.get('transaction_types', [])}
    for alias_key, alias_target in sorted(aliases.items(), key=lambda x: len(x[0]), reverse=True):
        if alias_target.lower() in tt_set:
            ak_pattern = re.escape(alias_key).replace('_', r'[\s_-]')
            if len(alias_key) <= 2 and not alias_key.isascii():
                pattern = rf'(?:^|(?<=\s)){ak_pattern}(?=\s|$)'
            else:
                pattern = rf'(?:^|(?<=\s)|(?<=\b)){ak_pattern}(?=\s|$|\b)'
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                remaining = (text[:m.start()] + text[m.end():]).strip()
                return alias_target, remaining

    # Fuzzy fallback: try matching each word against verbs and type names
    # Use higher cutoff than items — verb false positives are destructive
    all_verbs = {}  # verb_text -> trans_type
    for trans_type, verbs in config.get('action_verbs', {}).items():
        for v in verbs:
            all_verbs[v.lower()] = trans_type
    for tt in config.get('transaction_types', []):
        all_verbs[tt.lower()] = tt
    for alias_key, alias_target in aliases.items():
        if alias_target.lower() in tt_set:
            all_verbs[alias_key.lower()] = alias_target

    if all_verbs:
        words = text.split()
        for i, word in enumerate(words):
            w = word.strip()
            if not w or len(w) <= 2:
                continue
            cutoff = 0.85 if len(w) <= 4 else 0.75
            matches = get_close_matches(w.lower(), list(all_verbs.keys()),
                                        n=1, cutoff=cutoff)
            if matches:
                remaining = ' '.join(words[:i] + words[i+1:]).strip()
                return all_verbs[matches[0]], remaining

    return None, text


def _extract_supplier_info(text, config):
    all_locs = [l.lower() for l in config.get('locations', [])]
    default_source = config.get('default_source', 'warehouse')
    all_locs.append(default_source.lower())
    from_words = config.get('from_words', ['from'])
    for word in from_words:
        if len(word) <= 2 and not word.isascii():
            pattern = rf'{re.escape(word)}[\-\s]*(.+?)(?:\s*$)'
        else:
            pattern = rf'\b{re.escape(word)}\s+(.+?)(?:\s*$)'
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            supplier = m.group(1).strip()
            if supplier.lower() not in all_locs:
                remaining = text[:m.start()].strip()
                return supplier, remaining
    return None, text


def _extract_qty(text, config):
    remaining = text

    # "half a [container]"
    hm = re.search(r'\bhalf\s+a\s+', remaining, re.IGNORECASE)
    if hm:
        after = remaining[hm.end():]
        cont, after_cont = _extract_container(after, config)
        if cont:
            before = remaining[:hm.start()]
            remaining = (before + ' ' + after_cont).strip()
            return 0.5, cont, remaining

    # Math expressions: 2x17, 2x 17, 11*920
    mm = re.search(r'\b(\d+)\s*[x×*]\s*(\d+)\b', remaining)
    if mm:
        qty = int(mm.group(1)) * int(mm.group(2))
        remaining = (remaining[:mm.start()] + remaining[mm.end():]).strip()
        cont, remaining = _extract_container(remaining, config)
        return qty, cont, remaining

    # Plain number
    nm = re.search(r'\b(\d+)\b', remaining)
    if nm:
        qty = int(nm.group(1))
        remaining = (remaining[:nm.start()] + remaining[nm.end():]).strip()
        cont, remaining = _extract_container(remaining, config)
        return qty, cont, remaining

    return None, None, text


def _extract_container(text, config):
    containers = get_all_containers(config)

    # Expand with container aliases
    aliases = config.get('aliases', {})
    cont_lower_set = {c.lower() for c in containers}
    cont_alias_map = {}
    for alias_key, alias_target in aliases.items():
        if alias_target.lower() in cont_lower_set:
            cont_alias_map[alias_key] = alias_target
            containers.add(alias_key)

    for cont in sorted(containers, key=len, reverse=True):
        canonical = cont_alias_map.get(cont, cont)
        for variant in _container_variants(cont):
            # Try anchored first (container right after number)
            m = re.match(rf'{re.escape(variant)}\b', text.strip(), re.IGNORECASE)
            if m:
                remaining = text.strip()[m.end():].strip()
                return canonical, remaining
            # Then anywhere in text
            m = re.search(rf'\b{re.escape(variant)}\b', text, re.IGNORECASE)
            if m:
                remaining = (text[:m.start()] + text[m.end():]).strip()
                return canonical, remaining
    return None, text


def get_all_containers(config):
    containers = set()
    for convs in config.get('unit_conversions', {}).values():
        for key in convs:
            if key != 'base_unit':
                containers.add(key)
    return containers


def _container_variants(container):
    words = container.split()
    last = words[-1]
    variants = [container]
    # Only apply English pluralization rules to ASCII words
    if last.isascii():
        if last.endswith(('x', 's', 'sh', 'ch')):
            variants.append(' '.join(words[:-1] + [last + 'es']).strip())
        else:
            variants.append(' '.join(words[:-1] + [last + 's']).strip())
    return variants


def _convert_container(item, container, qty, config):
    convs = config.get('unit_conversions', {}).get(item, {})
    factor = convs.get(container)
    if factor is not None:
        return qty * factor
    return None


_DEFAULT_FILLER = [r"\bthat's\b", r'\bwhat\b', r'\bthe\b', r'\bof\b',
                    r'\ba\b', r'\ban\b', r'\bsome\b', r'\bvia\b']


def _remove_filler(text, config=None):
    filler = config.get('filler_words', _DEFAULT_FILLER) if config else _DEFAULT_FILLER
    for pattern in filler:
        # Plain words get wrapped in \b boundaries; regex patterns used as-is
        if not pattern.startswith('\\'):
            pattern = rf'\b{re.escape(pattern)}\b'
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


# ============================================================
# Item matching
# ============================================================

def _match_item(text, config):
    text_clean = text.strip()
    if not text_clean:
        return None, None
    text_lower = text_clean.lower()

    items = config.get('items', [])
    aliases = config.get('aliases', {})
    all_names = {i.lower(): i for i in items}
    all_aliases = {a.lower(): a for a in aliases}

    # 1. Exact substring match against canonical items (longest first)
    for item in sorted(items, key=len, reverse=True):
        if item.lower() in text_lower:
            return item, item

    # 2. Exact substring match against aliases (longest first)
    for alias in sorted(aliases, key=len, reverse=True):
        if alias.lower() in text_lower:
            return aliases[alias], alias

    # 3. Singular/plural normalization
    for item in sorted(items, key=len, reverse=True):
        il = item.lower()
        tl = text_lower.rstrip('s')
        if tl == il or tl == il.rstrip('s'):
            return item, text_clean

    # 4. Abbreviation/prefix match
    for item in sorted(items, key=len, reverse=True):
        if item.lower().startswith(text_lower):
            return item, text_clean

    # 5. Fuzzy match (whole text against items + aliases)
    # Short tokens need higher cutoff to prevent false positives
    # (e.g. תפוז/orange matching תפוא/potato at 0.75)
    all_targets = [i.lower() for i in items] + [a.lower() for a in aliases]
    fuzzy_cutoff = 0.8 if len(text_lower) <= 4 else 0.6
    matches = get_close_matches(text_lower, all_targets, n=1, cutoff=fuzzy_cutoff)
    if matches:
        return _resolve_match(matches[0], items, aliases), text_clean

    # 6. Try word spans (longest to shortest)
    words = text_lower.split()
    for span_len in range(min(len(words), 4), 0, -1):
        for start in range(len(words) - span_len + 1):
            span = ' '.join(words[start:start + span_len])

            # Exact alias
            if span in all_aliases:
                return aliases[all_aliases[span]], span
            # Exact item
            if span in all_names:
                return all_names[span], span
            # Fuzzy
            span_cutoff = 0.8 if len(span) <= 4 else 0.6
            matches = get_close_matches(span, all_targets, n=1, cutoff=span_cutoff)
            if matches:
                return _resolve_match(matches[0], items, aliases), span

    return None, None


def _resolve_match(match_lower, items, aliases):
    for alias, canonical in aliases.items():
        if alias.lower() == match_lower:
            return canonical
    for item in items:
        if item.lower() == match_lower:
            return item
    return None


# ============================================================
# Line merging
# ============================================================

def _merge_lines(parsed, config):
    if not parsed:
        return []

    merged = []
    i = 0
    while i < len(parsed):
        current = parsed[i]

        # Qty without item + next has item without qty → merge
        # But not if the qty line had text that failed item matching
        if (current['has_qty'] and not current['has_item']
                and not current.get('_unmatched_text')
                and i + 1 < len(parsed)):
            nxt = parsed[i + 1]
            if nxt['has_item'] and not nxt['has_qty']:
                combined = {**current}
                combined['item'] = nxt['item']
                combined['item_raw'] = nxt['item_raw']
                combined['has_item'] = True
                combined['raw'] = current['raw'] + '\n' + nxt['raw']
                # Apply container conversion now that we have both
                if combined['container'] and combined['item']:
                    conv = _convert_container(
                        combined['item'], combined['container'],
                        combined['qty'], config
                    )
                    if conv is not None:
                        combined['qty'] = conv
                        combined['container'] = None
                merged.append(combined)
                i += 2
                continue

        # Context-only line (verb/notes but no item/qty) → apply to previous
        if (not current['has_qty'] and not current['has_item']
                and (current['trans_type'] or current['notes_extra'])
                and not current['location']  # not a header with location
                and merged):
            prev = merged[-1]
            if current['trans_type'] and not prev['trans_type']:
                prev['trans_type'] = current['trans_type']
            if current['notes_extra']:
                prev['notes_extra'] = current['notes_extra']
            i += 1
            continue

        merged.append(current)
        i += 1

    return merged


# ============================================================
# Context broadcasting
# ============================================================

def _broadcast_context(items):
    if not items:
        return

    # Forward pass
    ctx_loc = ctx_dir = ctx_type = ctx_date = None
    for item in items:
        if item['location']:
            ctx_loc, ctx_dir = item['location'], item['direction']
        if item['trans_type']:
            ctx_type = item['trans_type']
        if item['date']:
            ctx_date = item['date']

        if not item['location'] and ctx_loc:
            item['location'], item['direction'] = ctx_loc, ctx_dir
        if not item['trans_type'] and ctx_type:
            item['trans_type'] = ctx_type
        if not item['date'] and ctx_date:
            item['date'] = ctx_date

    # Backward fill: find last-seen values from anywhere
    last_loc = last_dir = last_type = last_date = None
    for item in items:
        if item['location']:
            last_loc, last_dir = item['location'], item['direction']
        if item['date']:
            last_date = item['date']
        if item['trans_type']:
            last_type = item['trans_type']

    for item in items:
        if not item['location'] and last_loc:
            item['location'], item['direction'] = last_loc, last_dir
        if not item['date'] and last_date:
            item['date'] = last_date
        if not item['trans_type'] and last_type:
            item['trans_type'] = last_type


# ============================================================
# Result generation
# ============================================================

_NON_ZERO_SUM_DEFAULT = {'eaten', 'starting_point', 'recount', 'supplier_to_warehouse'}


def _generate_result(items, config, today):
    result = ParseResult()
    transaction_items = []

    for item in items:
        if item['has_item']:
            transaction_items.append(item)
        elif item['has_qty'] and not item['has_item']:
            result.unparseable.append(item['raw'])
        elif (item['trans_type'] and (item['location'] or item['date'])) \
                or (item['location'] and item['date']) \
                or (item['location'] and not item.get('_unmatched_text')):
            # Context-setting line (verb+destination, destination+date,
            # or standalone destination like לכ)
            pass
        else:
            if _is_note(item):
                result.notes.append(item['raw'])
            else:
                result.unparseable.append(item['raw'])

    _assign_batches(transaction_items)

    for item in transaction_items:
        rows = _item_to_rows(item, config, today)
        result.rows.extend(rows)

    return result


def _is_note(item):
    raw = item.get('raw', '')
    if not raw:
        return False
    alpha = len(re.findall(r'[a-zA-Z\u0590-\u05FF]', raw))
    if alpha == 0:
        return False
    return alpha / len(raw) > 0.3


def _assign_batches(items):
    if not items:
        return
    batch = 1
    prev_dest = items[0].get('location')
    prev_date = items[0].get('date')
    items[0]['batch'] = batch

    for item in items[1:]:
        dest = item.get('location')
        dt = item.get('date')
        if dest is not None and prev_dest is not None and dest != prev_dest:
            batch += 1
        elif dt is not None and prev_date is not None and dt != prev_date:
            batch += 1
        item['batch'] = batch
        if dest is not None:
            prev_dest = dest
        if dt is not None:
            prev_date = dt


def _item_to_rows(item, config, today):
    dt = item.get('date') or today
    inv_type = item.get('item', '???')
    qty = item['qty'] if item['qty'] is not None else 1
    trans_type = item.get('trans_type')
    location = item.get('location')
    batch = item.get('batch', 1)
    notes = item.get('notes_extra')
    default_source = config.get('default_source', 'warehouse')

    row_base = {
        'date': dt, 'inv_type': inv_type, 'batch': batch, 'notes': notes,
    }

    # Preserve unconverted container info for TUI learning prompt
    if item.get('container'):
        row_base['_container'] = item['container']
        row_base['_raw_qty'] = qty

    # Non-zero-sum → single row
    non_zero_sum = set(config.get('non_zero_sum_types', _NON_ZERO_SUM_DEFAULT))
    if trans_type in non_zero_sum:
        return [{**row_base,
                 'qty': qty,
                 'trans_type': trans_type,
                 'vehicle_sub_unit': location or default_source}]

    # Transfer to a different location → double-entry
    if location and location != default_source:
        if not trans_type:
            trans_type = config.get('default_transfer_type', 'warehouse_to_branch')
        direction = item.get('direction', 'to')
        if direction == 'from':
            # "from כ" → stock leaves כ, arrives at warehouse
            return [
                {**row_base, 'qty': -abs(qty), 'trans_type': trans_type,
                 'vehicle_sub_unit': location},
                {**row_base, 'qty': abs(qty), 'trans_type': trans_type,
                 'vehicle_sub_unit': default_source},
            ]
        return [
            {**row_base, 'qty': -abs(qty), 'trans_type': trans_type,
             'vehicle_sub_unit': default_source},
            {**row_base, 'qty': abs(qty), 'trans_type': trans_type,
             'vehicle_sub_unit': location},
        ]

    # Receiving at warehouse → single positive row
    if location and location == default_source:
        return [{**row_base, 'qty': abs(qty), 'trans_type': trans_type,
                 'vehicle_sub_unit': default_source}]

    # No location → single row with unknowns
    return [{**row_base, 'qty': qty, 'trans_type': trans_type,
             'vehicle_sub_unit': None}]
