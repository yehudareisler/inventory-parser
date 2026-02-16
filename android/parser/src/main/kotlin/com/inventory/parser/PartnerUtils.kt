package com.inventory.parser

/**
 * Double-entry partner detection and sync.
 * Ports find_partner() and update_partner() from inventory_core.py.
 */

fun findPartner(rows: List<Map<String, Any?>>, idx: Int): Int? {
    val row = rows[idx]
    val batch = row["batch"] ?: return null
    val item = row["inv_type"] ?: return null
    val qty = (row["qty"] as? Number)?.toDouble() ?: return null
    if (qty == 0.0) return null

    for (i in rows.indices) {
        if (i == idx) continue
        val other = rows[i]
        val otherQty = (other["qty"] as? Number)?.toDouble() ?: continue
        if (other["batch"] == batch
            && other["inv_type"] == item
            && otherQty * qty < 0
        ) {
            return i
        }
    }
    return null
}

fun updatePartner(rows: List<MutableMap<String, Any?>>, idx: Int, field: String, newValue: Any?) {
    val partnerIdx = findPartner(rows, idx) ?: return
    val partner = rows[partnerIdx]

    when (field) {
        "inv_type", "date", "trans_type", "batch" -> partner[field] = newValue
        "qty" -> {
            if (newValue is Number) {
                val v = -newValue.toDouble()
                partner["qty"] = if (v == v.toLong().toDouble()) v.toLong().toInt() else v
            }
        }
    }
}
