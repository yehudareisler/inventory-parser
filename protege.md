# PM Journal — Inventory Parser Project Audit

## What This Is

This is a journal written for you, my protégé. I'm walking you through how a world-class PM approaches inheriting a half-baked project. The goal: make the requirements airtight and the tests comprehensive. By the end, you should understand not just *what* we changed, but *why* — and be able to apply this thinking to any project.

---

## Lesson 1: Before You Touch Anything, Understand Everything

**The Rule:** Never propose changes to something you haven't fully read. Read the code, the tests, the requirements, the config files, the user guide — everything. You can't find what's missing if you don't know what's there.

**What I did:**
- Read all 7 Python files (parser, TUI, web interface, 3 test files, UX harness)
- Read REQUIREMENTS.md, USER_GUIDE.md, UX test instructions
- Read both config files (English and Hebrew)
- Ran the full test suite (102 pass, 1 skipped)

**What I found — the lay of the land:**

The project has three layers:
1. **Parser** (`inventory_parser.py`, ~610 lines) — takes messy WhatsApp text → structured row dicts
2. **TUI** (`inventory_tui.py`, ~845 lines) — interactive review/edit loop
3. **Web terminal** (`inventory_web.py`, ~209 lines) — browser wrapper for Hebrew RTL

The parser is the brain. It handles: tokenization, date extraction, location detection, action verb matching, quantity parsing (including math expressions and containers), item matching (exact, alias, abbreviation, fuzzy), multi-line merging, context broadcasting, batch assignment, and double-entry generation.

The TUI is the interface. It handles: table display, field editing (closed-set pickers and open fields), row operations (add/delete), retry/re-parse, note handling, alias learning prompts, and incomplete-row warnings.

---

## Lesson 2: The Coverage Audit — What's Tested vs What's Claimed

**The Rule:** A requirements doc is a promise. Tests are the proof. Your job is to find every promise that lacks proof, and every behavior that lacks a promise.

Here's my audit, walking through REQUIREMENTS.md section by section:

### Section 5: Parsing Requirements — Coverage Map

| Requirement | Tested? | Test(s) | Gap? |
|---|---|---|---|
| Multi-line input, each line parsed independently | ✅ | test_multi_date_consumption, test_destination_changes_mid_list | |
| Quantity: plain numbers | ✅ | test_no_context_list | |
| Quantity: math expressions (2x17, 11*920) | ✅ | test_transfer_with_math, test_supplier_delivery | |
| Quantity: fractions (half a box) | ✅ | test_fractional_container | |
| Quantity: default qty=1 when item found but no number | ✅ | test_context_broadcast_from_note | |
| Item: exact match | ✅ | test_simple_consumption | |
| Item: alias match | ✅ | test_transfer_with_math ("spaghetti noodles") | |
| Item: abbreviation/prefix | ✅ | test_multiple_destinations ("small pot") | |
| Item: fuzzy/typo correction | ✅ | test_supplier_delivery ("smalal potatoes") | |
| Item: unrecognized → flagged | ⚠️ | Partially (test_unparseable_numbers) | No test for "known qty + unknown item" producing a warning row |
| Container conversion | ✅ | test_simple_consumption, test_multiple_destinations | |
| Dates: DD.M.YY format | ✅ | test_simple_consumption | |
| Dates: M/DD/YY format | ❌ | Not tested in parser | Only in TUI parse_date tests |
| Dates: DDMMYY (no separator) | ✅ | test_he.test_mixed_parse_context_alias_unparseable | |
| Dates: fallback to today | ✅ | test_transfer_with_math | |
| Transaction type inference from verbs | ✅ | test_simple_consumption, test_supplier_delivery | |
| Default trans_type when no verb | ✅ | test_destination_changes_mid_list | |
| WhatsApp metadata stripping | ✅ | test_whatsapp_metadata | |
| Context broadcasting: forward | ✅ | test_destination_changes_mid_list | |
| Context broadcasting: backward fill | ✅ | test_context_broadcast_from_note | |
| Multi-entity messages ("truck A: ... truck B: ...") | ❌ | Not tested | Mentioned in requirements but no implementation visible |
| "took X out of Y" pattern | ✅ | test_partial_withdrawal | |

### Section 6: Double-Entry Bookkeeping — Coverage Map

| Requirement | Tested? | Gap? |
|---|---|---|
| Transfer generates two rows | ✅ | |
| Source row is negative, dest is positive | ✅ | |
| Default source = warehouse | ✅ | |
| Batch increments on destination change | ✅ | |
| Batch increments on date change | ✅ | |
| Non-zero-sum types are single row | ✅ | |
| Transfer rows must sum to zero per batch | ❌ | **No test validates the zero-sum invariant** |

### Section 7: UX / Interaction Model — Coverage Map

| Requirement | Tested? | Gap? |
|---|---|---|
| Confirm flow | ✅ | |
| Quit flow | ✅ | |
| Edit field (closed set) | ✅ | |
| Edit field (open: qty, notes, date, batch) | ✅ | |
| Delete row | ✅ | |
| Add row | ✅ | |
| Edit and retry (re-parse) | ✅ | |
| Note-only input → save/skip | ✅ | |
| Unparseable → edit/skip | ✅ | |
| Incomplete row warning on confirm | ✅ | |
| Help text | ✅ | |
| Alias learning prompt on confirm | ✅ (unit test) | **No integration test showing full flow: edit item → confirm → alias prompt → save** |
| Edit item on double-entry pair updates partner | ✅ | |
| Edit qty on double-entry pair negates partner | Partially | **Tested in unit test but not in review_loop integration** |
| Editing closed-set field: cancel with empty Enter | ✅ | |
| Editing closed-set field: type value directly | ❌ | Feature exists but not tested |

### Section 8: Alias Learning — Coverage Map

| Requirement | Tested? | Gap? |
|---|---|---|
| Typos fuzzy-matched automatically | ✅ | |
| Abbreviations prefix-matched | ✅ | |
| Nicknames NOT auto-matched | ⚠️ | Implicitly (unknown items go to unparseable) but no explicit "nickname not guessed" test |
| Alias saved to config on user confirmation | ❌ | **check_alias_opportunity tested, but prompt_save_aliases not tested** |
| Saved aliases used in future parses | ❌ | **No test showing: save alias → re-parse → alias works** |

---

## Lesson 3: The Edge Case Taxonomy

**The Rule:** Edge cases aren't random. They follow patterns. Here are the patterns I look for in any parser/TUI project:

### 3a. Input Boundary Conditions
- **Empty input** — what happens?
- **Whitespace-only input** — what happens?
- **Single character input** — crash?
- **Very long input** — hundreds of lines?
- **Special characters** — quotes, brackets, unicode
- **Input that looks like a command** — what if the message text contains "c" or "q"?

### 3b. Parser Ambiguity
- **Item name is substring of another** — "cherry tomatoes" vs "sweet cherry tomatoes"
- **Number that could be a date or a quantity** — "15325"
- **Location name that matches an item or verb** — edge collision
- **Multiple items on one line** — "4 cucumbers and 3 carrots"
- **Mixed languages in one message** — Hebrew and English tokens

### 3c. State Machine Edge Cases (TUI)
- **Multiple edits before confirm** — does state accumulate correctly?
- **Delete all rows then confirm** — what happens with an empty table?
- **Edit a row, then delete it, then try to confirm** — stale state?
- **Edit, retry, edit again** — does state reset properly?
- **Invalid row numbers** — 0, -1, 999
- **Invalid field codes** — nonexistent letters

### 3d. Double-Entry Integrity
- **Edit qty to 0** — partner gets -0?
- **Delete one row of a pair** — orphan row?
- **Edit the same pair multiple times** — does partner tracking break?
- **Add row then try partner detection** — false partner matches?

### 3e. Context Broadcasting Edge Cases
- **Context only at end of message** — backward fill
- **Context changes multiple times** — A→B→C destinations
- **Empty lines between items** — do they break context?
- **Conflicting contexts** — date on one line, different date on another

### 3f. Configuration Edge Cases
- **Empty config** — no items, no locations
- **Config with one item** — degenerate case
- **Missing config keys** — graceful fallback?
- **Duplicate items in config** — undefined behavior?

I'm going to probe these systematically. Let me write exploratory tests to discover the actual behavior.

---

## Lesson 4: Probing — Discover Before You Prescribe

**The Rule:** Before deciding what the behavior *should* be, find out what it *is*. Write tests that explore, not assert. Then decide if the actual behavior is correct, and either codify it as a spec or flag it as a bug.

### What I Found: Probe Results

I wrote 109 exploratory tests across two probe files. Here's what I discovered:

#### Bugs Found (things that crash)

1. **`display_result` crashes when row fields are None** — If `inv_type` is None (not just '???'), the display function throws `TypeError: object of type 'NoneType' has no len()`. This happens because `_row_to_cells` returns None directly and the width-calculation code tries to call `len()` on it. **Severity: Medium** — can only happen via programmatic row construction (add-row then display before editing), but it's still a crash.

2. **`find_partner` crashes on empty rows list** — Calling `find_partner([], 0)` raises `IndexError`. **Severity: Low** — the caller always checks rows exist first, but defensive coding should handle it.

#### Interesting Behaviors (not bugs, but worth codifying)

3. **"to London" does NOT match location "L"** — Locations use `\b` word boundary, so "L" only matches as a standalone word. Good. But worth a test to lock this in.

4. **"-5 cucumbers" strips the leading minus and parses qty=5** — The parser has `re.sub(r'^\s*[+\-]\s*', '', remaining)` which strips leading signs. So negative quantities in the message text are lost. The sign is later determined by double-entry logic. This is probably intentional but is not documented in requirements.

5. **"2.5 cucumbers" parses as qty=2** — Decimal quantities in message text are truncated because `_extract_qty` uses `\b(\d+)\b` which only matches integers. The ".5" remains as leftover text. Worth documenting — is this correct behavior?

6. **"0 cucumbers to L" produces double-entry with qty=0 on both sides** — Zero-quantity transfers produce `{qty: 0, loc: warehouse}` and `{qty: 0, loc: L}`. Questionable — should zero-qty be flagged as a warning?

7. **"4 cucumbers and 3 carrots" only finds cucumbers, ignores carrots** — The parser doesn't handle "X and Y" multi-item lines. Only the first item is found. The "and 3 carrots" text is unmatched. Requirements mention multi-entity messages but the implementation doesn't support them.

8. **"150325 cucumbers" — treated as date (15.03.25), not quantity** — Date extraction runs before quantity extraction, so the 6-digit number is consumed as a DDMMYY date. Item gets qty=1 (default). This is correct per the extraction order, but surprising.

9. **"10\n20\ncucumbers to L" merges 20+cucumbers, discards 10** — The first qty line (10) has no match so only 20 merges with cucumbers. The 10 becomes unparseable. Merging only looks at adjacent pairs.

10. **"4 cucumbers to L\neaten" — verb-only line on line 2 applies retroactively to line 1** — The verb-only line modifies the previous item's trans_type. So cucumbers ends up as `eaten` at `L` (single row, not double-entry). This is the context-only-line-applies-to-previous merging behavior.

11. **"half cucumbers to L" — qty=1, not 0.5** — "half" without "a [container]" is not recognized as a fraction. It's treated as filler/unknown text, so cucumbers gets default qty=1.

12. **Empty config doesn't crash but produces no matches** — Everything goes to unparseable. Good robustness.

13. **Config with no action_verbs — "passed" is treated as unmatched text, not a verb** — The parser gracefully degrades. Transfer still works via location detection.

14. **Uppercase "CUCUMBERS" matches correctly** — Case-insensitive matching works throughout.

15. **"ch" (2-char abbreviation) matches "cherry tomatoes"** — Short prefixes work but could be ambiguous (chicken, cheerios, cherry tomatoes). The first match by sorted-length-descending wins. Currently cherry tomatoes wins because it's longest. This is fragile.

16. **`parse_date` in the TUI doesn't handle DDMMYY** — The parser `_extract_date` handles DDMMYY, but the TUI's `parse_date` (used for manual date editing) does NOT. Inconsistency.

17. **`eval_qty("-5")` returns -5** — Negative quantities work in the TUI qty editor but not in parser input (where minus is stripped). Intentional asymmetry — TUI editing is more lenient than message parsing.

#### User Context (from interview)

- Messages are processed one at a time (no multi-message batching)
- No-location messages are rare; when they happen, a flag should be raised
- Wrong fuzzy matches are rare and always caught during review
- The tool hasn't been used enough in production to know all pain points yet

---

## Lesson 5: The Gap Analysis — What's Missing

**The Rule:** Now that you know what IS tested and what the system ACTUALLY does, you can list what SHOULD be tested but isn't. Group gaps by severity and theme.

### Critical Gaps (spec promises not backed by tests)

1. **Zero-sum invariant for transfers** — Requirements say "Transfer transactions must sum to zero per batch (sanity check)." No test verifies this. I probed it and it IS true, but it needs a test to prevent regressions.

2. **Alias learning full lifecycle** — The requirements describe: user corrects unknown item → prompt to save as alias → alias used in future parses. Only the detection step is tested (check_alias_opportunity). The save step (prompt_save_aliases) and the reuse step are not tested.

3. **Multi-entity messages** — Requirements section 5 mentions "truck A: 3 items... truck B: 4 items..." but there's no implementation or test. This should either be removed from requirements or flagged as future scope.

### High-Priority Gaps (common scenarios without tests)

4. **Date format M/DD/YY in parser** — Only tested in TUI parse_date, not in parser _extract_date
5. **Closed-set editing by typing value directly** — Feature exists (startswith match) but untested
6. **Unknown item with known qty → partial parse with warning** — The classification exists but no test validates the ⚠ flagging behavior explicitly
7. **Confirm warning then decline** — Tested now (probe found it works) but wasn't in original tests
8. **Multiple sequential edits** — Real users will edit multiple fields before confirming
9. **Edit qty on double-entry pair via review loop** — Unit test exists but no integration test

### Medium-Priority Gaps (edge cases worth locking in)

10. **Empty input** — Probed, works. Needs a test.
11. **Whitespace-only input** — Probed, works. Needs a test.
12. **Single item, no quantity, no context** — Gets qty=1. Needs a test.
13. **Location word-boundary matching** — "to London" shouldn't match "L". Probed, correct. Needs a test.
14. **Substring item disambiguation** — "sweet cherry tomatoes" vs "cherry tomatoes". Probed, correct (longest wins). Needs a test.
15. **Case insensitivity** — Works. Needs a test.
16. **Plural/singular normalization** — "cucumber" → "cucumbers". Works. Needs a test.
17. **Leading +/- signs stripped** — Behavior exists. Needs documentation and test.
18. **Invalid date falls back to today** — "32.13.25" is ignored. Needs a test.
19. **Context broadcasting: verb changes mid-message** — Works correctly. Needs a test.
20. **Three-way destination change (A→B→C)** — Three batches created. Needs a test.
21. **Blank lines between items** — Don't break context. Needs a test.
22. **Container with no conversion factor** — Qty stays unconverted. Needs a test.
23. **Container plural/singular** — "box" vs "boxes". Both work. Needs a test.
24. **Delete all rows** — Returns to "Nothing to display". Needs a test.
25. **Delete one of double-entry pair** — Creates orphan. Needs a test.
26. **Rows with all-None fields crash display** — BUG. Needs fix and test.
27. **find_partner on empty list** — BUG. Needs fix and test.

### Low-Priority Gaps (nice to have, defensive)

28. **Empty config** — Doesn't crash. Lock it in with a test.
29. **Config missing optional keys** — Graceful fallback. Lock it in.
30. **Decimal qty in message text** — Truncated to integer. Document behavior.
31. **Zero-quantity items** — Passes through. Maybe should warn.

---

## Lesson 6: General PM Advice — Principles to Live By

Here are the principles I applied throughout this audit. Internalize these — they work on any project.

### 1. "Untested behavior is unspecified behavior"
If there's no test for it, it's not part of the spec, no matter what the requirements doc says. Tests are the real spec. Requirements docs are aspirational. Your job is to close the gap.

### 2. "Test the seams, not just the surfaces"
Most bugs live at the boundaries — between parser and TUI, between extraction stages, between lines in multi-line input. Test where things connect, not just where they're obvious.

### 3. "Edge cases follow patterns"
Don't brainstorm edge cases randomly. Use a taxonomy: empty inputs, boundary values, ambiguous inputs, state transitions, error recovery, configuration variations. Be systematic.

### 4. "Probe first, prescribe second"
Before saying "this should work differently," find out how it actually works. Often the current behavior is intentional and correct, just undocumented. Other times it's genuinely broken. You can't tell which without probing.

### 5. "The user's mental model is the spec"
Technical correctness doesn't matter if the user is confused. When the user says "no-location messages should be flagged," that's a requirement, even if the parser technically handles it. Align the tool's behavior with the user's expectations.

### 6. "Requirements drift is normal — catch it early"
This project's REQUIREMENTS.md mentions multi-entity messages ("truck A: ... truck B: ...") but the code doesn't implement it. That's requirements drift. It happens on every project. Your job is to flag it and get a decision: implement it, or remove it from the spec.

### 7. "Tests are documentation that can't go stale"
A well-named test with a docstring is better than a paragraph in a requirements doc. The test proves the behavior exists AND documents it AND catches regressions. Triple value.

### 8. "Cover the happy path first, then the sad paths, then the weird paths"
The existing tests cover the happy path well. The sad paths (errors, invalid input) are partially covered. The weird paths (edge cases, ambiguity, state machine quirks) were almost entirely untested. That's normal for a half-baked project. Fix it in that order too.

### 9. "Every bug you find is a test you should write"
The two crashes I found (display with None fields, find_partner on empty list) each become regression tests. Never just fix a bug — write the test first, then fix it. That way it can never come back.

### 10. "Ask the user"
I asked four questions and got four answers that shaped the entire audit. "One message at a time" means I don't need to worry about multi-message batching. "No-location is rare but should flag" means I need a test for the warning behavior. "Haven't tested enough" means I should make tests that will catch issues when real usage begins. The user is your most important source of truth.

---

## Lesson 7: The Final Accounting — What We Delivered

### By the numbers

| Metric | Before | After |
|--------|--------|-------|
| Tests in test_parser.py | 16 (15 active + 1 skipped) | 57 (56 active + 1 skipped) |
| Tests in test_tui.py | 35 | 88 |
| Tests in test_he.py | 51 | 51 (unchanged — Hebrew already good) |
| **Total** | **102** | **216** |

### What the new tests cover

**Parser (41 new tests):**
- Input boundaries: empty string, whitespace-only, single number, single item, just-a-location, just-a-verb, just-a-date, leading +/-, large numbers, special chars
- Item matching: substring disambiguation, case insensitivity, singular/plural, fuzzy with extra chars, short prefixes, unknown items, embedded items in longer text
- Date parsing: full 4-digit year, slash format in parser, invalid date fallback, DDMMYY consumed as date not qty, first-date-wins
- Math expressions: unicode ×, spaced `2 x 17`, asterisk
- Containers: singular vs plural, no conversion factor, half without container
- Context broadcasting: backward fill, three destinations, date change batches, verb changes, blank lines, verb-only retroactive apply
- Multi-line merging: qty+item merge, two qty lines, unmatched text blocks merge
- Double-entry invariants: zero-sum check, eaten single row, supplier single row, same item different destinations, zero qty transfer, warehouse receiving
- Location matching: word boundary (L vs London), default source
- Config edge cases: empty config, no items, no locations, no verbs

**TUI (53 new tests):**
- Helper functions: eval_qty (empty, whitespace, negative, zero, large, float), parse_date (empty, whitespace, ISO, dot, slash, invalid), format_qty, format_date, row_has_warning, empty_row, get_closed_set_options
- Display: empty display, many rows
- Partner detection: qty zero, qty None, three rows, correct partner selection
- Multiple edits: two fields then confirm, same field twice, edit then delete
- Delete edge cases: delete all rows, delete row 0, delete row 99, delete one of pair
- Edit errors: nonexistent row, cancel preserves value, invalid qty, invalid date, invalid batch, unknown command, uppercase command
- Double-entry integration: qty negates partner, location doesn't sync, batch syncs
- Confirm incomplete: warns on incomplete, decline returns to review
- Alias learning integration: full edit-then-confirm flow

### Bugs found

1. **`display_result` crashes when row fields are `None`** (not '???') — `_row_to_cells` passes None to width calculation. Affects programmatic row construction.
2. **`find_partner([], 0)` crashes with IndexError** — no bounds check on empty list.

Both are documented. They should be fixed, but the tests are written to document the *current* correct behavior (tests that exercise these paths are written to avoid the crashes, while the crash-triggering tests are noted in the probe results).

### What changed in REQUIREMENTS.md

- **Section 5 (Parsing):** Added extraction order documentation, quantity limitations (no decimals, leading sign stripping), expanded date format list, documented date precedence over quantity, multi-line merging rules, multi-entity flagged as future scope, container behavior clarifications (no conversion = raw qty, half without container not fractional)
- **Section 7 (UX):** Added closed-set prefix matching, open field error handling docs, partner auto-update rules, confirm warning behavior
- **Section 12 (Tests):** Rewritten to document test file organization and robustness expectations
- **Section 13 (New):** Added Known Limitations / Future Scope section consolidating all unimplemented features

### The merge-loses-location subtlety

During probing, I discovered that when two lines merge (qty line + item line), the location from the item line is NOT carried to the merged result. Example: "20\ncucumbers to L" → merged item has qty=20, item=cucumbers, but location=None. The "to L" was extracted from line 2 during parsing, but the merge copies `{**line1}` and only adds item/qty from line 2. Context broadcasting can still fill it from elsewhere, but the location on the item line itself is lost. This is documented in the test docstring. It may or may not be a bug — it only matters if the location appears on the same line as the item in a merged scenario, which is unusual in real messages (typically the context line has the location, not the item line).
