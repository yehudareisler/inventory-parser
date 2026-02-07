"""UX test harness — step-by-step TUI session simulator.

Lets a test evaluator "interact" with the TUI by providing a JSON session:

  {
    "text": "passed 2x17 spaghetti noodles to L",
    "commands": ["?", "1t", "e", "c"]
  }

Outputs a transcript showing the screen after each command.

Usage:
  python3 ux_test_harness.py session.json
  python3 ux_test_harness.py < session.json
  echo '{"text":"4 cucumbers to L","commands":["c"]}' | python3 ux_test_harness.py
"""

import json
import sys
import io
import builtins

from inventory_parser import parse
from inventory_tui import review_loop, load_config


def run_session(text, commands, config):
    """Run a TUI session and return a step-by-step transcript."""
    result = parse(text, config)

    transcript = []
    step = [0]  # mutable counter
    captured = io.StringIO()

    original_print = builtins.print

    def capturing_print(*args, **kwargs):
        """Capture print output to our buffer AND original stdout."""
        # Write to capture buffer
        kwargs_buf = dict(kwargs)
        kwargs_buf['file'] = captured
        original_print(*args, **kwargs_buf)

    def mock_input(prompt=''):
        """Mock input that captures screen output between calls."""
        # Also capture the prompt itself
        captured.write(prompt)

        # Flush captured output as a transcript step
        screen = captured.getvalue()
        captured.truncate(0)
        captured.seek(0)

        if step[0] == 0:
            transcript.append(('INITIAL SCREEN', '', screen))
        else:
            cmd_label = commands[step[0] - 1] if step[0] - 1 < len(commands) else '???'
            transcript.append((f'STEP {step[0]}', cmd_label, screen))

        step[0] += 1

        # Return next command
        cmd_idx = step[0] - 1
        if cmd_idx < len(commands):
            return commands[cmd_idx]
        raise EOFError("No more commands")

    # Monkey-patch
    builtins.print = capturing_print
    builtins.input = mock_input

    try:
        outcome = review_loop(result, text, config)
    except EOFError:
        outcome = None
    finally:
        builtins.print = original_print
        builtins.input = builtins.__dict__.get('input', input)
        # Restore input properly
        import importlib
        importlib.reload(builtins)

    # Capture any remaining output
    remaining = captured.getvalue()
    if remaining.strip():
        transcript.append(('FINAL OUTPUT', '', remaining))

    return transcript, outcome


def format_transcript(transcript, outcome):
    """Format transcript as readable text."""
    lines = []

    for label, cmd, screen in transcript:
        if cmd:
            lines.append(f"\n{'=' * 60}")
            lines.append(f"=== {label}: User types \"{cmd}\"")
            lines.append(f"{'=' * 60}")
        else:
            lines.append(f"\n{'=' * 60}")
            lines.append(f"=== {label}")
            lines.append(f"{'=' * 60}")

        lines.append(screen.rstrip())

    lines.append(f"\n{'=' * 60}")
    lines.append("=== SESSION COMPLETE")
    lines.append(f"{'=' * 60}")

    if outcome is None:
        lines.append("Outcome: discarded (quit or no more commands)")
    else:
        rows = outcome.get('rows', [])
        notes = outcome.get('notes', [])
        lines.append(f"Outcome: confirmed ({len(rows)} rows, {len(notes)} notes)")

    return '\n'.join(lines)


def main():
    # Read session JSON
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        with open(sys.argv[1]) as f:
            session = json.load(f)
    else:
        session = json.load(sys.stdin)

    text = session['text']
    commands = session['commands']
    config_path = session.get('config', 'config.yaml')

    config = load_config(config_path)

    transcript, outcome = run_session(text, commands, config)
    print(format_transcript(transcript, outcome))


if __name__ == '__main__':
    main()
