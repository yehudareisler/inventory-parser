package com.inventory.parser

import java.time.LocalDate
import java.time.format.DateTimeFormatter

/**
 * Row formatting, date/qty helpers, math evaluator, date parser, empty row factory.
 * Ports format_date(), format_qty(), _format_cell(), _row_to_cells(),
 * format_rows_for_clipboard(), eval_qty(), parse_date(), empty_row()
 * from inventory_core.py.
 */

fun formatDate(d: Any?): String {
    return when (d) {
        is LocalDate -> d.format(DateTimeFormatter.ISO_LOCAL_DATE)
        null -> "???"
        else -> d.toString().ifEmpty { "???" }
    }
}

fun formatQty(q: Any?): String {
    if (q == null) return "???"
    if (q is Double && q == q.toLong().toDouble()) return q.toLong().toString()
    if (q is Float && q == q.toLong().toFloat()) return q.toLong().toString()
    return q.toString()
}

fun rowHasWarning(row: Map<String, Any?>, config: Map<String, Any?>? = null): Boolean {
    if (config != null) {
        val required = getRequiredFields(config)
        return required.any { row[it] == null }
    }
    return row["trans_type"] == null || row["vehicle_sub_unit"] == null
}

fun formatCell(row: Map<String, Any?>, field: String): String {
    return when (field) {
        "date" -> formatDate(row["date"])
        "qty" -> {
            val qtyStr = formatQty(row["qty"])
            val container = row["_container"] as? String
            if (container != null) "$qtyStr [$container?]" else qtyStr
        }
        "batch" -> (row["batch"] ?: "").toString()
        "notes" -> (row["notes"] as? String) ?: ""
        else -> {
            val v = row[field]
            v?.toString() ?: "???"
        }
    }
}

fun rowToCells(index: Int, row: Map<String, Any?>, config: Map<String, Any?>? = null): List<String> {
    val warn = if (rowHasWarning(row, config)) "\u26a0 " else ""
    val fieldOrder = if (config != null) getFieldOrder(config) else DEFAULT_FIELD_ORDER
    val cells = mutableListOf("$warn${index + 1}")
    for (field in fieldOrder) {
        cells.add(formatCell(row, field))
    }
    return cells
}

fun formatRowsForClipboard(rows: List<Map<String, Any?>>, config: Map<String, Any?>? = null): String {
    if (rows.isEmpty()) return ""
    val fieldOrder = if (config != null) getFieldOrder(config) else DEFAULT_FIELD_ORDER
    return rows.joinToString("\n") { row ->
        fieldOrder.joinToString("\t") { field -> formatCell(row, field) }
    }
}

private val MATH_PATTERN = Regex("""^(\d+)\s*[x×*]\s*(\d+)$""")

fun evalQty(text: String): Number? {
    val trimmed = text.trim()
    val m = MATH_PATTERN.matchEntire(trimmed)
    if (m != null) {
        return m.groupValues[1].toInt() * m.groupValues[2].toInt()
    }
    return try {
        val v = trimmed.toDouble()
        if (v == v.toLong().toDouble()) v.toLong().toInt() else v
    } catch (_: NumberFormatException) {
        null
    }
}

fun parseEditDate(text: String): LocalDate? {
    val trimmed = text.trim()

    // DD.MM.YY or DD.MM.YYYY
    val dotMatch = Regex("""(\d{1,2})\.(\d{1,2})\.(\d{2,4})$""").matchEntire(trimmed)
    if (dotMatch != null) {
        val day = dotMatch.groupValues[1].toInt()
        val month = dotMatch.groupValues[2].toInt()
        var year = dotMatch.groupValues[3].toInt()
        if (year < 100) year += 2000
        return try { LocalDate.of(year, month, day) } catch (_: Exception) { null }
    }

    // MM/DD/YY or MM/DD/YYYY
    val slashMatch = Regex("""(\d{1,2})/(\d{1,2})/(\d{2,4})$""").matchEntire(trimmed)
    if (slashMatch != null) {
        val month = slashMatch.groupValues[1].toInt()
        val day = slashMatch.groupValues[2].toInt()
        var year = slashMatch.groupValues[3].toInt()
        if (year < 100) year += 2000
        return try { LocalDate.of(year, month, day) } catch (_: Exception) { null }
    }

    // DDMMYY (6 digits)
    val sixDigit = Regex("""(\d{6})$""").matchEntire(trimmed)
    if (sixDigit != null) {
        val s = sixDigit.groupValues[1]
        val day = s.substring(0, 2).toInt()
        val month = s.substring(2, 4).toInt()
        val year = s.substring(4, 6).toInt() + 2000
        return try { LocalDate.of(year, month, day) } catch (_: Exception) { null }
    }

    // ISO format
    return try { LocalDate.parse(trimmed) } catch (_: Exception) { null }
}

fun emptyRow(): MutableMap<String, Any?> {
    return mutableMapOf(
        "date" to LocalDate.now(),
        "inv_type" to "???",
        "qty" to 0,
        "trans_type" to null,
        "vehicle_sub_unit" to null,
        "batch" to 1,
        "notes" to null,
    )
}
