package com.inventory.parser

/**
 * All user-facing strings, commands, and field codes.
 * Ports UIStrings class and _EN_DEFAULTS from inventory_core.py.
 */

val EN_DEFAULTS = mapOf(
    "commands" to mapOf(
        "confirm" to "c",
        "quit" to "q",
        "retry" to "r",
        "edit" to "e",
        "save_note" to "n",
        "skip" to "s",
        "delete_prefix" to "x",
        "add_row" to "+",
        "help" to "?",
        "yes" to "y",
        "no" to "n",
    ),
    "field_codes" to mapOf(
        "d" to "date",
        "i" to "inv_type",
        "q" to "qty",
        "t" to "trans_type",
        "l" to "vehicle_sub_unit",
        "n" to "notes",
        "b" to "batch",
    ),
    "field_display_names" to mapOf(
        "inv_type" to "ITEM",
        "trans_type" to "TRANS TYPE",
        "vehicle_sub_unit" to "LOCATION",
        "qty" to "QTY",
        "date" to "DATE",
        "notes" to "NOTES",
        "batch" to "BATCH",
    ),
    "table_headers" to listOf("#", "DATE", "ITEM", "QTY", "TYPE", "LOCATION", "BATCH", "NOTES"),
    "option_letters" to "abcdefghijklmnopqrstuvwxyz",
    "strings" to mapOf(
        "paste_prompt" to "\nPaste message ('exit' to quit, 'alias'/'convert' to add):",
        "exit_word" to "exit",
        "nothing_to_display" to "\nNothing to display.",
        "note_prefix" to "Note",
        "unparseable_prefix" to "Could not parse",
        "saved_note_prefix" to "Saved note",
        "no_transactions" to "\nNo transactions found.",
        "review_prompt" to "\n[c]onfirm / edit (e.g. 1i) / [r]etry / [q]uit  (? for help)",
        "notes_only_prompt" to "Save as [n]ote / [e]dit and retry / [s]kip  (? for help)",
        "unparseable_prompt" to "\n[e]dit and retry / [s]kip  (? for help)",
        "confirm_incomplete_warning" to "  Warning: Row(s) {row_list} have incomplete fields (???). Confirm anyway? [{yes}/{no}] ",
        "enter_letter_prompt" to "Enter letter (or Enter to cancel)> ",
        "edit_cancelled" to "  Edit cancelled.",
        "invalid_choice" to "  Invalid choice. Enter a letter ({first}-{last}).",
        "open_field_prompt" to "\n{display_name} (current: {current}, Enter to cancel)",
        "invalid_quantity" to "  Invalid quantity.",
        "invalid_date" to "  Invalid date. Use DD.MM.YY or YYYY-MM-DD.",
        "invalid_batch" to "  Invalid batch number.",
        "row_deleted" to "  Row {num} deleted.",
        "delete_partner_warning" to "  Note: Row {partner_num} is the double-entry partner and now standalone.",
        "invalid_row" to "  Invalid row number.",
        "row_updated" to "  Row {num} {field} → {value}",
        "unknown_command" to "  Unknown command. Type ? for help, or try e.g. 1{example_field} to edit {example_name} on row 1.",
        "original_text_label" to "\nOriginal text:\n{text}\n",
        "enter_corrected_text" to "Enter corrected text (empty line to finish):",
        "edit_line_prompt" to "Line # to edit (Enter to re-parse):",
        "edit_line_new" to "  New text (Enter to delete line):",
        "edit_line_updated" to "  Line {num} updated.",
        "edit_line_deleted" to "  Line {num} deleted.",
        "save_alias_prompt" to "Save \"{original}\" → \"{canonical}\" as alias? [{yes}/{no}] ",
        "title" to "=== Inventory Message Parser ===",
        "subtitle" to "Paste a WhatsApp message to parse. Type 'exit' to quit.\n",
        "goodbye" to "Goodbye.",
        "discarded" to "  Discarded.",
        "confirmed_title" to "\n=== Confirmed transactions ===",
        "confirmed_count" to "\n({count} row(s) confirmed)",
        "clipboard_copied" to "\n({count} row(s) copied to clipboard)",
        "clipboard_failed" to "\nCould not copy to clipboard. Showing table instead:",
        "config_not_found" to "Config file not found: {path}",
        "config_hint" to "Create one based on config.yaml.example",
        "help_commands_header" to "Commands:",
        "help_field_codes_header" to "Field codes:",
        "help_examples_header" to "Examples:",
        "help_confirm_desc" to "Confirm and save all rows",
        "help_quit_desc" to "Quit (discard this parse)",
        "help_retry_desc" to "Edit raw text and re-parse",
        "help_edit_desc" to "Edit a field (e.g., {example})",
        "help_delete_desc" to "Delete a row (e.g., {example})",
        "help_add_desc" to "Add a new empty row",
        "help_help_desc" to "Show this help",
        "help_save_note_desc" to "Save as note (keep the text for reference)",
        "help_skip_desc" to "Skip (discard this input)",
        "save_conversion_prompt" to "Save unit conversion? 1 {container} of {item} = ? ",
        "conversion_saved" to "  Saved: 1 {container} of {item} = {factor}",
        "cmd_alias" to "alias",
        "cmd_convert" to "convert",
        "alias_short_prompt" to "Alias (short name): ",
        "alias_maps_to_prompt" to "Maps to: ",
        "alias_saved" to "  Saved: {alias} → {item}",
        "convert_item_prompt" to "Item name: ",
        "convert_container_prompt" to "Container name: ",
        "convert_factor_prompt" to "How many units in 1 {container}: ",
        "fuzzy_confirm" to "  → {resolved}? [{yes}/{no}] ",
        "help_locations_header" to "Known locations:",
        "review_parse_btn" to "Parse",
        "review_confirm_btn" to "Confirm",
        "sheet_btn" to "Sheet",
        "clipboard_btn" to "Clipboard",
        "review_add_row_btn" to "+ Row",
        "sheets_written" to "\n({count} row(s) written to sheet)",
        "sheets_write_failed" to "  ⚠ Could not write to sheet: {error}",
    ),
)

class UiStrings(config: Map<String, Any?>) {
    @Suppress("UNCHECKED_CAST")
    private val ui = config["ui"] as? Map<String, Any?> ?: emptyMap()

    @Suppress("UNCHECKED_CAST")
    val commands: Map<String, String> = run {
        val defaults = EN_DEFAULTS["commands"] as Map<String, String>
        val overrides = ui["commands"] as? Map<String, String> ?: emptyMap()
        defaults + overrides
    }

    @Suppress("UNCHECKED_CAST")
    val fieldCodes: Map<String, String> = run {
        ui["field_codes"] as? Map<String, String>
            ?: EN_DEFAULTS["field_codes"] as Map<String, String>
    }

    @Suppress("UNCHECKED_CAST")
    val fieldDisplayNames: Map<String, String> = run {
        val defaults = EN_DEFAULTS["field_display_names"] as Map<String, String>
        val overrides = ui["field_display_names"] as? Map<String, String> ?: emptyMap()
        defaults + overrides
    }

    @Suppress("UNCHECKED_CAST")
    val tableHeaders: List<String> = run {
        ui["table_headers"] as? List<String>
            ?: EN_DEFAULTS["table_headers"] as List<String>
    }

    val optionLetters: String = run {
        ui["option_letters"] as? String
            ?: EN_DEFAULTS["option_letters"] as String
    }

    @Suppress("UNCHECKED_CAST")
    val strings: Map<String, String> = run {
        val defaults = EN_DEFAULTS["strings"] as Map<String, String>
        val overrides = ui["strings"] as? Map<String, String> ?: emptyMap()
        defaults + overrides
    }

    @Suppress("UNCHECKED_CAST")
    val items: List<String> = config["items"] as? List<String> ?: emptyList()

    @Suppress("UNCHECKED_CAST")
    val aliases: Map<String, String> = config["aliases"] as? Map<String, String> ?: emptyMap()

    /**
     * Get a UI string with optional format substitution.
     * Placeholders use {key} syntax matching Python str.format().
     */
    fun s(key: String, vararg args: Pair<String, Any>): String {
        var template = strings[key] ?: key
        for ((k, v) in args) {
            template = template.replace("{$k}", v.toString())
        }
        return template
    }

    fun fieldName(internalName: String): String {
        return fieldDisplayNames[internalName] ?: internalName.uppercase()
    }

    fun firstFieldCodeFor(internalName: String): String {
        for ((letter, field) in fieldCodes) {
            if (field == internalName) return letter
        }
        return "?"
    }
}
