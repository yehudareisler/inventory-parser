"""Google Sheets integration — read config data and write confirmed rows.

Thin wrapper around gspread.  Every function takes explicit parameters
(no module-level state) so callers can mock the client trivially.
"""

import gspread


# ============================================================
# Authentication
# ============================================================

def authenticate(credentials_file=None, token_file=None):
    """Return an authenticated gspread Client.

    If *credentials_file* is provided, uses gspread's OAuth flow
    (opens browser on first run, caches token in *token_file*).

    If *credentials_file* is omitted or None, falls back to
    Application Default Credentials — works if you've run:
        gcloud auth application-default login \\
            --scopes=https://www.googleapis.com/auth/spreadsheets
    """
    if credentials_file:
        token = token_file or 'token.json'

        def _no_browser_flow(client_config, scopes, port=0):
            """OAuth flow that doesn't try to auto-open a browser.

            Starts a local server and prints the URL for the user to
            open manually — works in WSL / headless environments.
            """
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_config(client_config, scopes)
            flow.run_local_server(port=port, open_browser=False)
            return flow.credentials

        return gspread.oauth(
            credentials_filename=credentials_file,
            authorized_user_filename=token,
            flow=_no_browser_flow,
        )

    # Application Default Credentials (gcloud CLI login)
    import google.auth
    from google.auth.transport.requests import Request
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds, _ = google.auth.default(scopes=scopes)
    creds.refresh(Request())
    return gspread.authorize(creds)


# ============================================================
# Readers
# ============================================================

def _get_worksheet(client, spreadsheet_id, sheet_name):
    """Open a spreadsheet by key and return the named worksheet."""
    return client.open_by_key(spreadsheet_id).worksheet(sheet_name)


def read_single_column(client, spreadsheet_id, sheet_name, cell_range):
    """Read a single-column range and return a flat list of non-empty strings.

    >>> read_single_column(client, sid, 'Ref', 'A2:A')
    ['cherry tomatoes', 'spaghetti', 'cucumbers']
    """
    ws = _get_worksheet(client, spreadsheet_id, sheet_name)
    values = ws.get_values(cell_range)
    return [row[0].strip() for row in values if row and row[0].strip()]


def read_key_value_columns(client, spreadsheet_id, sheet_name, cell_range):
    """Read a two-column range and return a dict  {col_A: col_B}.

    Used for aliases (alias → canonical name).
    """
    ws = _get_worksheet(client, spreadsheet_id, sheet_name)
    values = ws.get_values(cell_range)
    result = {}
    for row in values:
        if len(row) >= 2 and row[0].strip():
            result[row[0].strip()] = row[1].strip()
    return result


def read_action_verbs(client, spreadsheet_id, sheet_name, cell_range):
    """Read a two-column range (trans_type, comma-separated verbs) → dict.

    >>> read_action_verbs(client, sid, 'Ref', 'D2:E')
    {'warehouse_to_branch': ['passed', 'gave', 'sent'], ...}
    """
    ws = _get_worksheet(client, spreadsheet_id, sheet_name)
    values = ws.get_values(cell_range)
    result = {}
    for row in values:
        if len(row) >= 2 and row[0].strip():
            trans_type = row[0].strip()
            verbs = [v.strip() for v in row[1].split(',') if v.strip()]
            result[trans_type] = verbs
    return result


def read_unit_conversions(client, spreadsheet_id, sheet_name, cell_range):
    """Read a three-column range (item, container, factor) → nested dict.

    Returns the same structure as config['unit_conversions']:
    {'cherry tomatoes': {'small box': 990, 'box': 1980}, ...}
    """
    ws = _get_worksheet(client, spreadsheet_id, sheet_name)
    values = ws.get_values(cell_range)
    result = {}
    for row in values:
        if len(row) >= 3 and row[0].strip():
            item = row[0].strip()
            container = row[1].strip()
            try:
                factor = float(row[2])
                if factor == int(factor):
                    factor = int(factor)
            except (ValueError, TypeError):
                continue
            if item not in result:
                result[item] = {}
            result[item][container] = factor
    return result


# ============================================================
# Orchestrator — read all configured inputs
# ============================================================

# Fields that need specialised readers (everything else uses single-column).
_SPECIAL_READERS = {
    'aliases': read_key_value_columns,
    'action_verbs': read_action_verbs,
    'unit_conversions': read_unit_conversions,
}


def load_sheet_config(client, spreadsheet_id, input_mappings):
    """Read all configured input ranges and return a dict to overlay on config.

    *input_mappings* comes from ``config['google_sheets']['input']``.
    """
    overlay = {}
    for field_name, mapping in input_mappings.items():
        sheet_name = mapping['sheet']
        cell_range = mapping['range']

        reader = _SPECIAL_READERS.get(field_name)
        if reader:
            overlay[field_name] = reader(client, spreadsheet_id,
                                         sheet_name, cell_range)
        else:
            overlay[field_name] = read_single_column(client, spreadsheet_id,
                                                     sheet_name, cell_range)
    return overlay


# ============================================================
# Writers
# ============================================================

def append_rows(client, spreadsheet_id, sheet_name, rows, field_order):
    """Append confirmed transaction rows to the output sheet.

    Returns the number of rows appended.
    """
    if not rows:
        return 0

    from inventory_core import _format_cell

    ws = _get_worksheet(client, spreadsheet_id, sheet_name)
    values = [[_format_cell(row, f) for f in field_order] for row in rows]
    ws.append_rows(values, value_input_option='USER_ENTERED')
    return len(values)


def append_alias(client, spreadsheet_id, sheet_name, alias, target):
    """Append a single [alias, target] row to the aliases sheet."""
    ws = _get_worksheet(client, spreadsheet_id, sheet_name)
    ws.append_row([alias, target], value_input_option='USER_ENTERED')


def append_conversion(client, spreadsheet_id, sheet_name, item, container, factor):
    """Append a single [item, container, factor] row to the conversions sheet."""
    ws = _get_worksheet(client, spreadsheet_id, sheet_name)
    ws.append_row([item, container, factor], value_input_option='USER_ENTERED')
