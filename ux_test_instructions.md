# UX Evaluation Instructions

You are evaluating a text-based inventory management tool. Pretend you have never seen this tool before. Your job is to try using it and report on the user experience — what's intuitive, what's confusing, what needs better help.

## How the test harness works

You interact with the tool by writing JSON session files and running them through a harness. The harness feeds your commands to the tool and captures what the screen shows after each command.

**Session format:**
```json
{
  "text": "the inventory message to parse",
  "commands": ["command1", "command2", "..."]
}
```

**Running a session:**
```bash
echo '{"text":"4 cucumbers to L","commands":["c"]}' | python3 ux_test_harness.py
```

Or save to a file:
```bash
echo '{"text":"...","commands":["..."]}' > /tmp/claude-1000/-mnt-c-Users-Owner-claude-code-projects/30edc5c3-3b60-452f-a8f3-5985b75d4225/scratchpad/session.json
python3 ux_test_harness.py /tmp/claude-1000/-mnt-c-Users-Owner-claude-code-projects/30edc5c3-3b60-452f-a8f3-5985b75d4225/scratchpad/session.json
```

The output is a step-by-step transcript showing what appeared on screen after each command.

**Important:** You must guess what commands to type based on what the screen shows. If you get stuck, try `?` — the tool may have a help command.

## Tasks

Complete these tasks in order. For each task, write the session JSON, run it, read the transcript, and report your experience.

### Task A: Read the user guide

Read the file `USER_GUIDE.md`. Before running anything, write down:
1. What you understood immediately
2. What was unclear or ambiguous
3. What questions you still have after reading

### Task B: Basic workflows

Try these four scenarios. For each one, create a session with just enough commands to complete the flow (confirm, skip, or quit).

1. **Simple consumption:** Parse this text and confirm:
   ```
   eaten by L 15.3.25\n2 small boxes cherry tomatoes\n4 cucumbers
   ```

2. **Transfer with math:** Parse and confirm:
   ```
   passed 2x17 spaghetti noodles to L
   ```

3. **Note (not a transaction):** Parse this and handle appropriately:
   ```
   Rimon to N via naor by phone
   ```

4. **Unparseable gibberish:** Parse this and handle appropriately:
   ```
   4 82 95 3 1
   ```

For each scenario, report:
- Did the screen output make sense?
- Did you know what to type next without looking at the guide?
- If you used `?` for help, was it sufficient?
- What (if anything) would have made it clearer?

### Task C: Editing

Try these editing operations. You may need to experiment with the command syntax.

1. Parse `eaten by L\n4 cucumbers` and change the quantity to `2x17` (should become 34)
2. Parse `4 cucumbers to L` and change the transaction type to `eaten`
3. Parse `passed 4 spaghetti to L` and change the item to `cherry tomatoes` — check if the partner row also updates
4. Parse `eaten by L\n4 cucumbers\n2 spaghetti` and delete the first row
5. Parse `eaten by L\n4 cucumbers` and add a new row

For each, report:
- Was the `<row><field>` syntax obvious from the screen? Or did you need help?
- Did you remember the field codes, or did you need to look them up?
- Any surprises in how editing worked?

### Task D: Error recovery

Try these error scenarios:

1. Parse `4 cucumbers to L` and type an invalid/unknown command (like `z` or `edit`)
2. Parse `eaten by L\n4 cucumbers` and try to edit a non-existent row (like `5q`)
3. Parse `eaten by L\n4 cucumbers`, use retry (`r`), and enter different text

Report:
- Were error messages clear and helpful?
- Did you always know how to recover from a mistake?
- Any commands that silently failed or behaved unexpectedly?

### Task E: Overall assessment

Write a UX evaluation report covering:

1. **First impressions** — What worked well right out of the box?
2. **Confusion points** — Where did you get stuck or need to think?
3. **Missing affordances** — What hints, labels, or messages would have prevented your confusion?
4. **Concrete suggestions** — List specific, actionable changes to make the interface more self-explanatory. Be precise (e.g., "Add text X after Y" rather than "improve error messages").
5. **Intuitiveness ratings** (1-5 scale, 5 = immediately obvious):
   - (a) Basic confirm flow (paste → review → confirm)
   - (b) Field editing (`<row><field>` syntax)
   - (c) Error recovery (invalid commands, retry)
   - (d) Help and discoverability
