"""
JSON-driven parser tests.

Loads test cases from test_data/ and runs them against the Python parser.
Same JSON files will be used by the Kotlin parser test runner to ensure parity.

Usage:
    python3 -m pytest test_parser_json.py -v
"""

import json
import copy
import os
from datetime import date
from pathlib import Path

import pytest

from inventory_parser import parse, fuzzy_resolve


# ============================================================
# Paths
# ============================================================

TEST_DATA = Path(__file__).parent / 'test_data'
CONFIGS_DIR = TEST_DATA / 'configs'
CASES_DIR = TEST_DATA / 'cases' / 'parser'


# ============================================================
# Config loading
# ============================================================

_config_cache = {}


def _load_config(config_id):
    """Load a config fixture by ID, handling 'extends'."""
    if config_id in _config_cache:
        return copy.deepcopy(_config_cache[config_id])

    path = CONFIGS_DIR / f'{config_id}.json'
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    if 'extends' in data:
        base = _load_config(data['extends'])
        for k, v in data.items():
            if k not in ('id', 'extends'):
                base[k] = v
        _config_cache[config_id] = base
        return copy.deepcopy(base)

    _config_cache[config_id] = data
    return copy.deepcopy(data)


def _apply_overrides(config, overrides):
    """Apply config_overrides, handling special keys."""
    for key, value in overrides.items():
        if key == 'aliases_add':
            config.setdefault('aliases', {}).update(value)
        elif key == 'items_add':
            config.setdefault('items', []).extend(value)
        else:
            config[key] = value
    return config


# ============================================================
# Date handling
# ============================================================

def _parse_date_str(s, today):
    """Convert a date string from JSON to a Python date."""
    if s is None:
        return None
    if s == 'TODAY':
        return today
    return date.fromisoformat(s)


def _parse_today(test_group):
    """Get the 'today' date for a test group."""
    today_str = test_group.get('today', '2025-03-19')
    return date.fromisoformat(today_str)


# ============================================================
# Test collection
# ============================================================

def _collect_test_cases():
    """Collect all test cases from JSON files for parametrize."""
    cases = []
    for json_file in sorted(CASES_DIR.glob('*.json')):
        with open(json_file, encoding='utf-8') as f:
            group = json.load(f)

        today = _parse_today(group)
        base_config_id = group.get('config')

        for test in group.get('tests', []):
            test_id = f"{group.get('group', json_file.stem)}::{test['name']}"
            cases.append(pytest.param(
                group, test, today, base_config_id,
                id=test_id,
            ))
    return cases


# ============================================================
# Assertion helpers
# ============================================================

def _check_row_fields(actual_row, expected_row, today, test_name, row_idx):
    """Check that actual_row matches all fields specified in expected_row."""
    for field, expected_val in expected_row.items():
        actual_val = actual_row.get(field)
        if field == 'date':
            expected_val = _parse_date_str(expected_val, today)
        assert actual_val == expected_val, (
            f"{test_name} row[{row_idx}].{field}: "
            f"expected {expected_val!r}, got {actual_val!r}"
        )


def _run_assertions(assertions, rows, notes, unparseable, test_name, today):
    """Run all assertion checks from the assertions dict."""
    for key, value in assertions.items():
        if key == 'row_count':
            assert len(rows) == value, (
                f"{test_name}: expected {value} rows, got {len(rows)}")
        elif key == 'row_count_gte':
            assert len(rows) >= value, (
                f"{test_name}: expected >= {value} rows, got {len(rows)}")
        elif key == 'notes_count':
            assert len(notes) == value, (
                f"{test_name}: expected {value} notes, got {len(notes)}")
        elif key == 'unparseable_count':
            assert len(unparseable) == value, (
                f"{test_name}: expected {value} unparseable, got {len(unparseable)}")
        elif key == 'unparseable_count_gt':
            assert len(unparseable) > value, (
                f"{test_name}: expected > {value} unparseable, got {len(unparseable)}")
        elif key == 'batch_sum_zero':
            batch_sums = {}
            for row in rows:
                b = row['batch']
                batch_sums[b] = batch_sums.get(b, 0) + row['qty']
            for batch_num in value:
                assert batch_sums.get(batch_num, 0) == 0, (
                    f"{test_name}: batch {batch_num} sums to "
                    f"{batch_sums.get(batch_num, 'N/A')}, expected 0")
        elif key == 'field_contains':
            for path, substr in value.items():
                row_idx_str, field = path.split('.', 1)
                row_idx = int(row_idx_str)
                actual = rows[row_idx].get(field) or ''
                assert substr in actual, (
                    f"{test_name}: row[{row_idx}].{field} should contain "
                    f"{substr!r}, got {actual!r}")
        elif key == 'notes_contains':
            for idx_str, substr in value.items():
                idx = int(idx_str)
                assert substr in notes[idx], (
                    f"{test_name}: notes[{idx}] should contain {substr!r}")
        elif key == 'all_rows_have':
            for field, expected_val in value.items():
                if field == 'date':
                    expected_val = _parse_date_str(expected_val, today)
                for i, row in enumerate(rows):
                    actual = row.get(field)
                    assert actual == expected_val, (
                        f"{test_name}: row[{i}].{field}: expected "
                        f"{expected_val!r}, got {actual!r}")
        elif key == 'any_row_has':
            converted = {
                f: (_parse_date_str(v, today) if f == 'date' else v)
                for f, v in value.items()
            }
            found = False
            for row in rows:
                if all(row.get(f) == v for f, v in converted.items()):
                    found = True
                    break
            assert found, (
                f"{test_name}: no row matches {value}")
        elif key == 'field_not_equal':
            for path, forbidden_val in value.items():
                row_idx_str, field = path.split('.', 1)
                row_idx = int(row_idx_str)
                actual = rows[row_idx].get(field)
                assert actual != forbidden_val, (
                    f"{test_name}: row[{row_idx}].{field} should NOT be "
                    f"{forbidden_val!r}")
        elif key == 'abs_qty':
            for idx_str, expected_abs in value.items():
                idx = int(idx_str)
                actual = abs(rows[idx]['qty'])
                assert actual == expected_abs, (
                    f"{test_name}: abs(row[{idx}].qty): expected "
                    f"{expected_abs}, got {actual}")
        elif key == 'qty_gt':
            for idx_str, threshold in value.items():
                idx = int(idx_str)
                actual = rows[idx]['qty']
                assert actual > threshold, (
                    f"{test_name}: row[{idx}].qty should be > {threshold}, "
                    f"got {actual}")
        elif key == 'no_unparseable_contains':
            for text in unparseable:
                assert value not in text, (
                    f"{test_name}: unparseable should not contain {value!r}")
        elif key == 'unparseable_contains':
            for idx_str, substr in value.items():
                idx = int(idx_str)
                assert substr in unparseable[idx], (
                    f"{test_name}: unparseable[{idx}] should contain "
                    f"{substr!r}, got {unparseable[idx]!r}")
        else:
            raise ValueError(f"Unknown assertion type: {key}")


# ============================================================
# Test runner
# ============================================================

@pytest.mark.parametrize("group, test_case, today, base_config_id",
                         _collect_test_cases())
def test_json(group, test_case, today, base_config_id):
    """Run a single JSON-defined test case."""
    test_name = test_case['name']
    function = test_case.get('function', 'parse')

    # --- fuzzy_resolve tests ---
    if function == 'fuzzy_resolve':
        fi = test_case['fuzzy_input']
        result, match_type = fuzzy_resolve(
            fi['text'], fi['items'], fi.get('aliases', {}))
        ef = test_case['expected_fuzzy']
        assert result == ef['result'], (
            f"{test_name}: fuzzy result expected {ef['result']!r}, "
            f"got {result!r}")
        assert match_type == ef['match_type'], (
            f"{test_name}: match_type expected {ef['match_type']!r}, "
            f"got {match_type!r}")
        return

    # --- parse tests ---
    # Build config
    if 'config_inline' in test_case:
        config = test_case['config_inline']
    else:
        config_id = test_case.get('config', base_config_id)
        config = _load_config(config_id)

    overrides = test_case.get('config_overrides', {})
    if overrides:
        _apply_overrides(config, overrides)

    # Parse
    result = parse(test_case['input'], config, today=today)
    rows = result.rows
    notes = result.notes
    unparseable = result.unparseable

    # Check expected_rows (partial field matching)
    expected_rows = test_case.get('expected_rows', [])
    for i, expected_row in enumerate(expected_rows):
        assert i < len(rows), (
            f"{test_name}: expected row[{i}] but only {len(rows)} rows")
        _check_row_fields(rows[i], expected_row, today, test_name, i)

    # Check expected_notes
    expected_notes = test_case.get('expected_notes')
    if expected_notes is not None and len(expected_notes) > 0:
        assert notes == expected_notes, (
            f"{test_name}: notes mismatch")

    # Check expected_unparseable
    expected_unp = test_case.get('expected_unparseable')
    if expected_unp is not None and len(expected_unp) > 0:
        assert unparseable == expected_unp, (
            f"{test_name}: unparseable mismatch")

    # Run assertions
    assertions = test_case.get('assertions', {})
    _run_assertions(assertions, rows, notes, unparseable, test_name, today)
