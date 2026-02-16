package com.inventory.parser

/**
 * Alias and unit-conversion learning opportunity detection.
 * Ports check_alias_opportunity() and check_conversion_opportunity()
 * from inventory_core.py.
 */

/**
 * Check if any edited items should be saved as aliases.
 * Returns list of (original, canonical) pairs.
 */
fun checkAliasOpportunity(
    rows: List<Map<String, Any?>>,
    originalTokens: Map<Int, String>,
    config: Map<String, Any?>
): List<Pair<String, String>> {
    @Suppress("UNCHECKED_CAST")
    val aliases = config["aliases"] as? Map<String, String> ?: emptyMap()
    @Suppress("UNCHECKED_CAST")
    val items = (config["items"] as? List<String> ?: emptyList()).map { it.lowercase() }
    val prompts = mutableListOf<Pair<String, String>>()

    for ((idx, original) in originalTokens) {
        if (idx >= rows.size) continue
        val canonical = rows[idx]["inv_type"] as? String ?: continue
        if (original.isEmpty() || canonical.isEmpty()) continue
        if (original == "???" || canonical == "???") continue

        val origLower = original.lowercase()
        val canonLower = canonical.lowercase()

        if (origLower == canonLower) continue
        if (aliases.keys.any { it.lowercase() == origLower }) continue
        if (origLower in items) continue

        prompts.add(original to canonical)
    }

    return prompts
}

/**
 * Check if any rows have unconverted containers that could be saved.
 * Returns list of (item, container) pairs.
 */
fun checkConversionOpportunity(
    rows: List<Map<String, Any?>>,
    config: Map<String, Any?>
): List<Pair<String, String>> {
    @Suppress("UNCHECKED_CAST")
    val convs = config["unit_conversions"] as? Map<String, Map<String, Any?>> ?: emptyMap()
    val seen = mutableSetOf<Pair<String, String>>()
    val prompts = mutableListOf<Pair<String, String>>()

    for (row in rows) {
        val container = row["_container"] as? String ?: continue
        val item = row["inv_type"] as? String ?: continue
        if (item == "???") continue

        val key = item to container
        if (key in seen) continue
        seen.add(key)

        if (convs[item]?.get(container) != null) continue

        prompts.add(key)
    }

    return prompts
}
