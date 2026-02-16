"""Tests for Google Sheets integration.

All tests mock gspread — no real API calls are made.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_worksheet():
    """A mock gspread Worksheet."""
    ws = Mock()
    ws.get_values = Mock(return_value=[])
    ws.append_rows = Mock()
    ws.append_row = Mock()
    return ws


@pytest.fixture
def mock_client(mock_worksheet):
    """A mock gspread Client with one spreadsheet + worksheet."""
    client = Mock()
    spreadsheet = Mock()
    spreadsheet.worksheet = Mock(return_value=mock_worksheet)
    client.open_by_key = Mock(return_value=spreadsheet)
    return client


@pytest.fixture
def config():
    """Minimal config dict for testing."""
    return {
        'items': ['cherry tomatoes', 'spaghetti', 'cucumbers'],
        'locations': ['L', 'C'],
        'transaction_types': ['warehouse_to_branch', 'eaten'],
        'default_source': 'warehouse',
        'aliases': {},
        'unit_conversions': {},
    }


# ============================================================
# Authentication
# ============================================================

class TestAuthenticate:
    @patch('inventory_sheets.gspread')
    def test_oauth_called_with_credentials(self, mock_gspread):
        from inventory_sheets import authenticate
        authenticate('client_secret.json')
        mock_gspread.oauth.assert_called_once()
        call_kwargs = mock_gspread.oauth.call_args[1]
        assert call_kwargs['credentials_filename'] == 'client_secret.json'
        assert call_kwargs['authorized_user_filename'] == 'token.json'
        assert 'flow' in call_kwargs

    @patch('inventory_sheets.gspread')
    def test_oauth_with_custom_token_file(self, mock_gspread):
        from inventory_sheets import authenticate
        authenticate('creds.json', token_file='my_token.json')
        mock_gspread.oauth.assert_called_once()
        call_kwargs = mock_gspread.oauth.call_args[1]
        assert call_kwargs['credentials_filename'] == 'creds.json'
        assert call_kwargs['authorized_user_filename'] == 'my_token.json'

    @patch('inventory_sheets.gspread')
    def test_returns_client(self, mock_gspread):
        from inventory_sheets import authenticate
        mock_gspread.oauth.return_value = Mock()
        client = authenticate('creds.json')
        assert client is mock_gspread.oauth.return_value


# ============================================================
# Read single column
# ============================================================

class TestReadSingleColumn:
    def test_returns_flat_list(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['cherry tomatoes'], ['spaghetti'], ['cucumbers']
        ]
        from inventory_sheets import read_single_column
        result = read_single_column(mock_client, 'sid', 'Ref', 'A2:A')
        assert result == ['cherry tomatoes', 'spaghetti', 'cucumbers']

    def test_skips_empty_rows(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['cherry tomatoes'], [''], ['cucumbers']
        ]
        from inventory_sheets import read_single_column
        result = read_single_column(mock_client, 'sid', 'Ref', 'A2:A')
        assert result == ['cherry tomatoes', 'cucumbers']

    def test_skips_whitespace_only_rows(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['cherry tomatoes'], ['   '], ['cucumbers']
        ]
        from inventory_sheets import read_single_column
        result = read_single_column(mock_client, 'sid', 'Ref', 'A2:A')
        assert result == ['cherry tomatoes', 'cucumbers']

    def test_empty_sheet(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = []
        from inventory_sheets import read_single_column
        result = read_single_column(mock_client, 'sid', 'Ref', 'A2:A')
        assert result == []

    def test_strips_whitespace(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [['  cherry tomatoes  ']]
        from inventory_sheets import read_single_column
        result = read_single_column(mock_client, 'sid', 'Ref', 'A2:A')
        assert result == ['cherry tomatoes']

    def test_skips_empty_inner_lists(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['cherry tomatoes'], [], ['cucumbers']
        ]
        from inventory_sheets import read_single_column
        result = read_single_column(mock_client, 'sid', 'Ref', 'A2:A')
        assert result == ['cherry tomatoes', 'cucumbers']


# ============================================================
# Read key-value columns (aliases)
# ============================================================

class TestReadKeyValueColumns:
    def test_returns_dict(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['cherry tom', 'cherry tomatoes'],
            ['spag', 'spaghetti'],
        ]
        from inventory_sheets import read_key_value_columns
        result = read_key_value_columns(mock_client, 'sid', 'Aliases', 'A2:B')
        assert result == {'cherry tom': 'cherry tomatoes', 'spag': 'spaghetti'}

    def test_skips_empty_keys(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['', 'cherry tomatoes'],
            ['spag', 'spaghetti'],
        ]
        from inventory_sheets import read_key_value_columns
        result = read_key_value_columns(mock_client, 'sid', 'Aliases', 'A2:B')
        assert result == {'spag': 'spaghetti'}

    def test_skips_short_rows(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['cherry tom'],  # missing second column
            ['spag', 'spaghetti'],
        ]
        from inventory_sheets import read_key_value_columns
        result = read_key_value_columns(mock_client, 'sid', 'Aliases', 'A2:B')
        assert result == {'spag': 'spaghetti'}

    def test_strips_whitespace(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['  cherry tom  ', '  cherry tomatoes  '],
        ]
        from inventory_sheets import read_key_value_columns
        result = read_key_value_columns(mock_client, 'sid', 'Aliases', 'A2:B')
        assert result == {'cherry tom': 'cherry tomatoes'}

    def test_empty_sheet(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = []
        from inventory_sheets import read_key_value_columns
        result = read_key_value_columns(mock_client, 'sid', 'Aliases', 'A2:B')
        assert result == {}


# ============================================================
# Read action verbs
# ============================================================

class TestReadActionVerbs:
    def test_parses_comma_separated_verbs(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['warehouse_to_branch', 'passed, gave, sent'],
            ['eaten', 'eaten, consumed'],
        ]
        from inventory_sheets import read_action_verbs
        result = read_action_verbs(mock_client, 'sid', 'Ref', 'D2:E')
        assert result == {
            'warehouse_to_branch': ['passed', 'gave', 'sent'],
            'eaten': ['eaten', 'consumed'],
        }

    def test_skips_empty_trans_type(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['', 'passed, gave'],
            ['eaten', 'eaten'],
        ]
        from inventory_sheets import read_action_verbs
        result = read_action_verbs(mock_client, 'sid', 'Ref', 'D2:E')
        assert 'eaten' in result
        assert '' not in result

    def test_strips_whitespace(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['  eaten  ', '  eaten , consumed  '],
        ]
        from inventory_sheets import read_action_verbs
        result = read_action_verbs(mock_client, 'sid', 'Ref', 'D2:E')
        assert result == {'eaten': ['eaten', 'consumed']}


# ============================================================
# Read unit conversions
# ============================================================

class TestReadUnitConversions:
    def test_builds_nested_dict(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['cherry tomatoes', 'small box', '990'],
            ['cherry tomatoes', 'box', '1980'],
            ['spaghetti', 'pack', '500'],
        ]
        from inventory_sheets import read_unit_conversions
        result = read_unit_conversions(mock_client, 'sid', 'Conv', 'A2:C')
        assert result == {
            'cherry tomatoes': {'small box': 990, 'box': 1980},
            'spaghetti': {'pack': 500},
        }

    def test_float_factor(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['milk', 'carton', '1.5'],
        ]
        from inventory_sheets import read_unit_conversions
        result = read_unit_conversions(mock_client, 'sid', 'Conv', 'A2:C')
        assert result == {'milk': {'carton': 1.5}}

    def test_skips_invalid_factor(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['milk', 'carton', 'abc'],
            ['spaghetti', 'pack', '500'],
        ]
        from inventory_sheets import read_unit_conversions
        result = read_unit_conversions(mock_client, 'sid', 'Conv', 'A2:C')
        assert result == {'spaghetti': {'pack': 500}}

    def test_skips_short_rows(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [
            ['milk', 'carton'],  # missing factor
            ['spaghetti', 'pack', '500'],
        ]
        from inventory_sheets import read_unit_conversions
        result = read_unit_conversions(mock_client, 'sid', 'Conv', 'A2:C')
        assert result == {'spaghetti': {'pack': 500}}

    def test_empty_sheet(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = []
        from inventory_sheets import read_unit_conversions
        result = read_unit_conversions(mock_client, 'sid', 'Conv', 'A2:C')
        assert result == {}


# ============================================================
# load_sheet_config orchestrator
# ============================================================

class TestLoadSheetConfig:
    def test_single_column_field(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [['apple'], ['banana']]
        from inventory_sheets import load_sheet_config
        mappings = {'items': {'sheet': 'Ref', 'range': 'A2:A'}}
        overlay = load_sheet_config(mock_client, 'sid', mappings)
        assert overlay['items'] == ['apple', 'banana']

    def test_aliases_field(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [['tom', 'tomatoes']]
        from inventory_sheets import load_sheet_config
        mappings = {'aliases': {'sheet': 'Aliases', 'range': 'A2:B'}}
        overlay = load_sheet_config(mock_client, 'sid', mappings)
        assert overlay['aliases'] == {'tom': 'tomatoes'}

    def test_action_verbs_field(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [['eaten', 'ate, consumed']]
        from inventory_sheets import load_sheet_config
        mappings = {'action_verbs': {'sheet': 'Ref', 'range': 'D2:E'}}
        overlay = load_sheet_config(mock_client, 'sid', mappings)
        assert overlay['action_verbs'] == {'eaten': ['ate', 'consumed']}

    def test_unit_conversions_field(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.return_value = [['milk', 'carton', '6']]
        from inventory_sheets import load_sheet_config
        mappings = {'unit_conversions': {'sheet': 'Conv', 'range': 'A2:C'}}
        overlay = load_sheet_config(mock_client, 'sid', mappings)
        assert overlay['unit_conversions'] == {'milk': {'carton': 6}}

    def test_empty_mappings(self, mock_client):
        from inventory_sheets import load_sheet_config
        overlay = load_sheet_config(mock_client, 'sid', {})
        assert overlay == {}


# ============================================================
# append_rows (transactions)
# ============================================================

class TestAppendRows:
    def test_appends_formatted_rows(self, mock_client, mock_worksheet):
        from inventory_sheets import append_rows
        rows = [{
            'date': date(2025, 3, 19),
            'inv_type': 'cherry tomatoes',
            'qty': 100,
            'trans_type': 'warehouse_to_branch',
            'vehicle_sub_unit': 'L',
            'batch': 1,
            'notes': '',
        }]
        field_order = ['date', 'inv_type', 'qty', 'trans_type',
                       'vehicle_sub_unit', 'batch', 'notes']
        count = append_rows(mock_client, 'sid', 'Trans', rows, field_order)
        assert count == 1
        mock_worksheet.append_rows.assert_called_once()
        appended = mock_worksheet.append_rows.call_args[0][0]
        assert appended[0][0] == '2025-03-19'
        assert appended[0][1] == 'cherry tomatoes'
        assert appended[0][2] == '100'

    def test_empty_rows_skips_api_call(self, mock_client, mock_worksheet):
        from inventory_sheets import append_rows
        count = append_rows(mock_client, 'sid', 'Trans', [], ['date'])
        assert count == 0
        mock_worksheet.append_rows.assert_not_called()

    def test_user_entered_value_input(self, mock_client, mock_worksheet):
        from inventory_sheets import append_rows
        rows = [{'date': date(2025, 1, 1), 'inv_type': 'x', 'qty': 1,
                 'trans_type': 't', 'vehicle_sub_unit': 'L', 'batch': 1,
                 'notes': ''}]
        append_rows(mock_client, 'sid', 'Trans', rows,
                    ['date', 'inv_type', 'qty', 'trans_type',
                     'vehicle_sub_unit', 'batch', 'notes'])
        kwargs = mock_worksheet.append_rows.call_args[1]
        assert kwargs['value_input_option'] == 'USER_ENTERED'

    def test_multiple_rows(self, mock_client, mock_worksheet):
        from inventory_sheets import append_rows
        rows = [
            {'date': date(2025, 1, 1), 'inv_type': 'a', 'qty': 1,
             'trans_type': 't', 'vehicle_sub_unit': 'L', 'batch': 1,
             'notes': ''},
            {'date': date(2025, 1, 2), 'inv_type': 'b', 'qty': 2,
             'trans_type': 't', 'vehicle_sub_unit': 'C', 'batch': 2,
             'notes': 'note'},
        ]
        count = append_rows(mock_client, 'sid', 'Trans', rows,
                            ['date', 'inv_type', 'qty', 'trans_type',
                             'vehicle_sub_unit', 'batch', 'notes'])
        assert count == 2
        appended = mock_worksheet.append_rows.call_args[0][0]
        assert len(appended) == 2


# ============================================================
# append_alias
# ============================================================

class TestAppendAlias:
    def test_appends_alias_row(self, mock_client, mock_worksheet):
        from inventory_sheets import append_alias
        append_alias(mock_client, 'sid', 'Aliases', 'cherry tom',
                     'cherry tomatoes')
        mock_worksheet.append_row.assert_called_once_with(
            ['cherry tom', 'cherry tomatoes'],
            value_input_option='USER_ENTERED',
        )


# ============================================================
# append_conversion
# ============================================================

class TestAppendConversion:
    def test_appends_conversion_row(self, mock_client, mock_worksheet):
        from inventory_sheets import append_conversion
        append_conversion(mock_client, 'sid', 'Conv', 'cherry tomatoes',
                          'small box', 990)
        mock_worksheet.append_row.assert_called_once_with(
            ['cherry tomatoes', 'small box', 990],
            value_input_option='USER_ENTERED',
        )


# ============================================================
# load_config_with_sheets (in inventory_core)
# ============================================================

class TestLoadConfigWithSheets:
    @patch('inventory_core.load_config')
    def test_no_sheets_section_returns_none(self, mock_load):
        mock_load.return_value = {'items': ['item1']}
        from inventory_core import load_config_with_sheets
        config, client = load_config_with_sheets('config.yaml')
        assert config['items'] == ['item1']
        assert client is None

    @patch('inventory_sheets.load_sheet_config')
    @patch('inventory_sheets.authenticate')
    @patch('inventory_core.load_config')
    def test_sheet_overlay_replaces_yaml(self, mock_load, mock_auth,
                                         mock_load_sheet):
        mock_load.return_value = {
            'items': ['old'],
            'google_sheets': {
                'credentials_file': 'creds.json',
                'spreadsheet_id': 'sid',
                'input': {'items': {'sheet': 'Ref', 'range': 'A2:A'}},
            },
        }
        mock_auth.return_value = Mock()
        mock_load_sheet.return_value = {'items': ['from_sheet']}

        from inventory_core import load_config_with_sheets
        config, client = load_config_with_sheets('config.yaml')
        assert config['items'] == ['from_sheet']
        assert client is not None

    @patch('inventory_sheets.load_sheet_config')
    @patch('inventory_sheets.authenticate')
    @patch('inventory_core.load_config')
    def test_sheet_fields_tracked(self, mock_load, mock_auth,
                                   mock_load_sheet):
        mock_load.return_value = {
            'items': ['old'],
            'aliases': {'a': 'b'},
            'google_sheets': {
                'credentials_file': 'creds.json',
                'spreadsheet_id': 'sid',
                'input': {
                    'items': {'sheet': 'Ref', 'range': 'A2:A'},
                    'aliases': {'sheet': 'Aliases', 'range': 'A2:B'},
                },
            },
        }
        mock_auth.return_value = Mock()
        mock_load_sheet.return_value = {
            'items': ['from_sheet'],
            'aliases': {'x': 'y'},
        }

        from inventory_core import load_config_with_sheets
        config, _ = load_config_with_sheets('config.yaml')
        assert config['_sheet_fields'] == {'items', 'aliases'}


# ============================================================
# save_config strips sheet-managed fields
# ============================================================

class TestSaveConfig:
    def test_strips_sheet_fields(self, tmp_path):
        from inventory_core import save_config, load_config
        config = {
            'items': ['from_sheet'],
            'aliases': {'x': 'y'},
            'default_source': 'warehouse',
            '_sheet_fields': {'items', 'aliases'},
            'google_sheets': {'spreadsheet_id': 'sid'},
        }
        path = tmp_path / 'test_config.yaml'
        save_config(config, str(path))
        saved = load_config(str(path))
        assert 'items' not in saved
        assert 'aliases' not in saved
        assert saved['default_source'] == 'warehouse'
        assert saved['google_sheets'] == {'spreadsheet_id': 'sid'}
        assert '_sheet_fields' not in saved

    def test_no_sheet_fields_saves_everything(self, tmp_path):
        from inventory_core import save_config, load_config
        config = {
            'items': ['local'],
            'aliases': {'a': 'b'},
        }
        path = tmp_path / 'test_config.yaml'
        save_config(config, str(path))
        saved = load_config(str(path))
        assert saved['items'] == ['local']
        assert saved['aliases'] == {'a': 'b'}


# ============================================================
# save_learned_alias
# ============================================================

class TestSaveLearnedAlias:
    def test_yaml_managed_saves_to_yaml(self, tmp_path):
        from inventory_core import save_learned_alias, load_config
        config = {'aliases': {}}
        path = tmp_path / 'cfg.yaml'
        path.write_text('aliases: {}\n')

        save_learned_alias(config, str(path), None, 'tom', 'tomatoes')

        assert config['aliases']['tom'] == 'tomatoes'
        saved = load_config(str(path))
        assert saved['aliases']['tom'] == 'tomatoes'

    def test_sheet_managed_appends_to_sheet(self, mock_client, mock_worksheet):
        from inventory_core import save_learned_alias
        config = {
            'aliases': {},
            '_sheet_fields': {'aliases'},
            'google_sheets': {
                'spreadsheet_id': 'sid',
                'output': {
                    'aliases': {'sheet': 'Aliases'},
                },
            },
        }

        save_learned_alias(config, '/fake/path', mock_client, 'tom', 'tomatoes')

        assert config['aliases']['tom'] == 'tomatoes'
        mock_worksheet.append_row.assert_called_once_with(
            ['tom', 'tomatoes'],
            value_input_option='USER_ENTERED',
        )

    def test_sheet_managed_but_no_output_is_in_memory_only(self):
        from inventory_core import save_learned_alias
        config = {
            'aliases': {},
            '_sheet_fields': {'aliases'},
            'google_sheets': {
                'spreadsheet_id': 'sid',
                'output': {},  # no aliases output
            },
        }

        save_learned_alias(config, '/fake/path', None, 'tom', 'tomatoes')

        # In-memory config is updated
        assert config['aliases']['tom'] == 'tomatoes'
        # But nothing was persisted (no YAML write, no sheet write)


# ============================================================
# save_learned_conversion
# ============================================================

class TestSaveLearnedConversion:
    def test_yaml_managed_saves_to_yaml(self, tmp_path):
        from inventory_core import save_learned_conversion, load_config
        config = {'unit_conversions': {}}
        path = tmp_path / 'cfg.yaml'
        path.write_text('unit_conversions: {}\n')

        save_learned_conversion(config, str(path), None,
                                'milk', 'carton', 6)

        assert config['unit_conversions']['milk']['carton'] == 6
        saved = load_config(str(path))
        assert saved['unit_conversions']['milk']['carton'] == 6

    def test_sheet_managed_appends_to_sheet(self, mock_client, mock_worksheet):
        from inventory_core import save_learned_conversion
        config = {
            'unit_conversions': {},
            '_sheet_fields': {'unit_conversions'},
            'google_sheets': {
                'spreadsheet_id': 'sid',
                'output': {
                    'unit_conversions': {'sheet': 'Conv'},
                },
            },
        }

        save_learned_conversion(config, '/fake/path', mock_client,
                                'milk', 'carton', 6)

        assert config['unit_conversions']['milk']['carton'] == 6
        mock_worksheet.append_row.assert_called_once_with(
            ['milk', 'carton', 6],
            value_input_option='USER_ENTERED',
        )


# ============================================================
# Error handling
# ============================================================

class TestErrorHandling:
    @patch('inventory_sheets.gspread')
    def test_auth_failure_propagates(self, mock_gspread):
        mock_gspread.oauth.side_effect = Exception("Bad credentials")
        from inventory_sheets import authenticate
        with pytest.raises(Exception, match="Bad credentials"):
            authenticate('bad_creds.json')

    def test_read_api_error_propagates(self, mock_client, mock_worksheet):
        mock_worksheet.get_values.side_effect = Exception("API error")
        from inventory_sheets import read_single_column
        with pytest.raises(Exception, match="API error"):
            read_single_column(mock_client, 'sid', 'Ref', 'A2:A')

    def test_append_rows_api_error_propagates(self, mock_client, mock_worksheet):
        mock_worksheet.append_rows.side_effect = Exception("quota exceeded")
        from inventory_sheets import append_rows
        rows = [{'date': date(2025, 1, 1), 'inv_type': 'x', 'qty': 1,
                 'trans_type': 't', 'vehicle_sub_unit': 'L',
                 'batch': 1, 'notes': ''}]
        with pytest.raises(Exception, match="quota exceeded"):
            append_rows(mock_client, 'sid', 'Trans', rows,
                        ['date', 'inv_type', 'qty', 'trans_type',
                         'vehicle_sub_unit', 'batch', 'notes'])
