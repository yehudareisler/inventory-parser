package com.inventory.parser

import java.time.LocalDate

// ============================================================
// Metadata stripping
// ============================================================

private val METADATA_PATTERNS = listOf(
    Regex("<This message was edited>", RegexOption.IGNORE_CASE),
    Regex("<Media omitted>", RegexOption.IGNORE_CASE),
)

private fun stripMetadata(text: String): String {
    var result = text
    for (pattern in METADATA_PATTERNS) {
        result = pattern.replace(result, "")
    }
    return result.trim()
}

// ============================================================
// Default filler words
// ============================================================

private val DEFAULT_FILLER = listOf(
    "\\bthat's\\b", "\\bwhat\\b", "\\bthe\\b", "\\bof\\b",
    "\\ba\\b", "\\ban\\b", "\\bsome\\b", "\\bvia\\b"
)

// ============================================================
// Default non-zero-sum types
// ============================================================

private val NON_ZERO_SUM_DEFAULT = setOf("eaten", "starting_point", "recount", "supplier_to_warehouse")

// ============================================================
// Whitespace splitting helper (matches Python's str.split())
// ============================================================

/**
 * Split on whitespace, discarding empty strings. Equivalent to Python's str.split().
 */
private fun splitWords(text: String): List<String> =
    text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }

// ============================================================
// Config helpers -- access Map<String, Any?> safely
// ============================================================

@Suppress("UNCHECKED_CAST")
private fun Map<String, Any?>.stringList(key: String, default: List<String> = emptyList()): List<String> {
    val v = this[key] ?: return default
    return (v as? List<*>)?.filterIsInstance<String>() ?: default
}

@Suppress("UNCHECKED_CAST")
private fun Map<String, Any?>.stringMap(key: String, default: Map<String, String> = emptyMap()): Map<String, String> {
    val v = this[key] ?: return default
    return (v as? Map<*, *>)?.entries?.associate { (k, v2) -> k.toString() to v2.toString() } ?: default
}

@Suppress("UNCHECKED_CAST")
private fun Map<String, Any?>.stringListMap(key: String, default: Map<String, List<String>> = emptyMap()): Map<String, List<String>> {
    val v = this[key] ?: return default
    val map = v as? Map<*, *> ?: return default
    return map.entries.associate { (k, v2) ->
        k.toString() to ((v2 as? List<*>)?.map { it.toString() } ?: emptyList())
    }
}

@Suppress("UNCHECKED_CAST")
private fun Map<String, Any?>.unitConversionsMap(): Map<String, Map<String, Number>> {
    val v = this["unit_conversions"] ?: return emptyMap()
    val map = v as? Map<*, *> ?: return emptyMap()
    return map.entries.associate { (k, v2) ->
        k.toString() to ((v2 as? Map<*, *>)?.entries?.associate { (k2, v3) ->
            k2.toString() to (v3 as? Number ?: (v3.toString().toDoubleOrNull() ?: 0))
        } ?: emptyMap())
    }
}

// ============================================================
// Public API
// ============================================================

/**
 * Parse an inventory message into structured rows.
 *
 * @param text The raw message text
 * @param config Configuration map (Python dict-style)
 * @param today The date to use as default (defaults to today)
 * @return ParseResult with rows, notes, and unparseable lines
 */
fun parse(text: String, config: Map<String, Any?>, today: LocalDate = LocalDate.now()): ParseResult {
    val stripped = stripMetadata(text)
    val lines = stripped.split("\n").map { it.trim() }.filter { it.isNotEmpty() }
    val parsed = lines.map { parseLine(it, config) }
    val merged = mergeLines(parsed, config)
    broadcastContext(merged)
    return generateResult(merged, config, today)
}

// ============================================================
// Line parsing
// ============================================================

private fun parseLine(text: String, config: Map<String, Any?>): MutableMap<String, Any?> {
    val r = mutableMapOf<String, Any?>(
        "raw" to text,
        "qty" to null, "item" to null, "item_raw" to null,
        "container" to null, "trans_type" to null,
        "location" to null, "direction" to null,
        "date" to null, "notes_extra" to null,
        "has_qty" to false, "has_item" to false,
    )

    var remaining = text

    // Strip leading +/-
    remaining = Regex("^\\s*[+\\-]\\s*").replaceFirst(remaining, "").trim()

    // Special pattern: "took X out of Y [item]"
    val took = Regex("took\\s+(\\d+)\\s+out\\s+of\\s+(\\d+)\\s+(.+)", RegexOption.IGNORE_CASE)
        .matchAt(remaining, 0)
    if (took != null) {
        r["qty"] = took.groupValues[1].toInt()
        r["has_qty"] = true
        r["notes_extra"] = "had ${took.groupValues[2]} total"
        val (item, raw) = matchItem(took.groupValues[3].trim(), config)
        if (item != null) {
            r["item"] = item
            r["item_raw"] = raw
            r["has_item"] = true
        }
        return r
    }

    // Extract date
    val (dateVal, afterDate) = extractDate(remaining)
    remaining = afterDate
    if (dateVal != null) {
        r["date"] = dateVal
    }

    // Extract location with direction
    val (loc, direction, afterLoc) = extractLocation(remaining, config)
    remaining = afterLoc
    if (loc != null) {
        r["location"] = loc
        r["direction"] = direction
    }

    // Extract action verb
    val (transType, afterVerb) = extractVerb(remaining, config)
    remaining = afterVerb
    if (transType != null) {
        r["trans_type"] = transType
    }

    // Extract supplier info ("from [name]") if relevant
    val fromWords = config.stringList("from_words", listOf("from"))
    if (fromWords.any { fw -> remaining.lowercase().contains(fw.lowercase()) }) {
        val (supplier, afterSupplier) = extractSupplierInfo(remaining, config)
        if (supplier != null) {
            r["notes_extra"] = "from $supplier"
            remaining = afterSupplier
        }
    }

    // Extract quantity + container
    val remainingBeforeQty = remaining
    val (qty, container, afterQty) = extractQty(remaining, config)
    remaining = afterQty
    if (qty != null) {
        r["qty"] = qty
        r["has_qty"] = true
    }
    if (container != null) {
        r["container"] = container
    }

    // Clean up remaining text and match item
    remaining = removeFiller(remaining, config)
    if (remaining.trim().isNotEmpty()) {
        val (item, raw) = matchItem(remaining, config)
        if (item != null) {
            r["item"] = item
            r["item_raw"] = raw
            r["has_item"] = true
        } else {
            r["_unmatched_text"] = remaining.trim()
        }
    }

    // Multi-number disambiguation: if item wasn't found, try other numbers as qty
    if (r["has_item"] == false && r["has_qty"] == true) {
        val allNumbers = Regex("\\b(\\d+)\\b").findAll(remainingBeforeQty)
            .map { it.groupValues[1] }.toList()
        if (allNumbers.size > 1) {
            for (numStr in allNumbers) {
                if (numStr.toInt() == (r["qty"] as? Number)?.toInt()) {
                    continue
                }
                val trialQty = numStr.toInt()
                var trialText = remainingBeforeQty.replaceFirst(numStr, "").trim()
                trialText = removeFiller(trialText, config)
                val (trialCont, trialAfter) = extractContainer(trialText, config)
                val (trialItem, trialRaw) = matchItem(
                    if (trialCont != null) trialAfter else trialText, config
                )
                if (trialItem != null) {
                    r["qty"] = trialQty
                    r["has_qty"] = true
                    r["item"] = trialItem
                    r["item_raw"] = trialRaw
                    r["has_item"] = true
                    r.remove("_unmatched_text")
                    if (trialCont != null) {
                        r["container"] = trialCont
                    }
                    break
                }
            }
        }
    }

    // Apply container conversion if we have item + container + qty
    if (r["item"] != null && r["container"] != null && r["qty"] != null) {
        val converted = convertContainer(
            r["item"] as String, r["container"] as String, r["qty"] as Number, config
        )
        if (converted != null) {
            r["qty"] = converted
            r["container"] = null
        }
    }

    return r
}

// ============================================================
// Extraction helpers
// ============================================================

private fun extractDate(text: String): Pair<LocalDate?, String> {
    // DD.MM.YY or DD.MM.YYYY
    var m = Regex("\\b(\\d{1,2})\\.(\\d{1,2})\\.(\\d{2,4})\\b").find(text)
    if (m != null) {
        val day = m.groupValues[1].toInt()
        val month = m.groupValues[2].toInt()
        var year = m.groupValues[3].toInt()
        if (year < 100) year += 2000
        val remaining = (text.substring(0, m.range.first) + text.substring(m.range.last + 1)).trim()
        try {
            return LocalDate.of(year, month, day) to remaining
        } catch (_: Exception) {
            // Invalid date, fall through
        }
    }

    // MM/DD/YY
    m = Regex("\\b(\\d{1,2})/(\\d{1,2})/(\\d{2,4})\\b").find(text)
    if (m != null) {
        val month = m.groupValues[1].toInt()
        val day = m.groupValues[2].toInt()
        var year = m.groupValues[3].toInt()
        if (year < 100) year += 2000
        val remaining = (text.substring(0, m.range.first) + text.substring(m.range.last + 1)).trim()
        try {
            return LocalDate.of(year, month, day) to remaining
        } catch (_: Exception) {
            // Invalid date, fall through
        }
    }

    // DDMMYY (6 digits, no separators)
    m = Regex("\\b(\\d{6})\\b").find(text)
    if (m != null) {
        val s = m.groupValues[1]
        val day = s.substring(0, 2).toInt()
        val month = s.substring(2, 4).toInt()
        val year = s.substring(4, 6).toInt() + 2000
        val remaining = (text.substring(0, m.range.first) + text.substring(m.range.last + 1)).trim()
        try {
            return LocalDate.of(year, month, day) to remaining
        } catch (_: Exception) {
            // Invalid date, fall through
        }
    }

    return null to text
}

private data class LocationResult(val location: String?, val direction: String?, val remaining: String)

private fun extractLocation(text: String, config: Map<String, Any?>): LocationResult {
    val locations = config.stringList("locations").toMutableList()
    val defaultSource = config["default_source"]?.toString() ?: "warehouse"
    val allLocs = locations.toMutableList()
    if (defaultSource !in allLocs) {
        allLocs.add(defaultSource)
    }

    // Expand with location aliases (aliases whose target is a known location)
    val aliases = config.stringMap("aliases")
    val locSet = allLocs.map { it.lowercase() }.toMutableSet()
    val locAliasMap = mutableMapOf<String, String>()
    for ((aliasKey, aliasTarget) in aliases) {
        if (aliasTarget in allLocs || aliasTarget.lowercase() in locSet) {
            locAliasMap[aliasKey] = aliasTarget
            if (aliasKey !in allLocs) {
                allLocs.add(aliasKey)
            }
        }
    }

    // Configurable prepositions: {direction: [words]}
    val defaultPreps = mapOf(
        "to" to listOf("to", "into"),
        "by" to listOf("by"),
        "from" to listOf("from"),
    )
    val prepConfig = config.stringListMap("prepositions", defaultPreps)

    for (loc in allLocs.sortedByDescending { it.length }) {
        for ((direction, preps) in prepConfig) {
            for (prep in preps.sortedByDescending { it.length }) {
                val pattern: Regex
                if (prep.length <= 2 && !prep.isAscii()) {
                    // For short/non-ASCII prepositions (e.g., Hebrew characters)
                    pattern = Regex(
                        "(?:^|\\s)${Regex.escape(prep)}[\\-\\s]*${Regex.escape(loc)}(?=\\s|$)",
                        RegexOption.IGNORE_CASE
                    )
                } else {
                    pattern = Regex(
                        "\\b${Regex.escape(prep)}\\s+(?:the\\s+)?${Regex.escape(loc)}\\b",
                        RegexOption.IGNORE_CASE
                    )
                }
                val matchResult = pattern.find(text)
                if (matchResult != null) {
                    var start = matchResult.range.first
                    if (start < text.length && text[start].isWhitespace()) {
                        start += 1
                    }
                    val remaining = (text.substring(0, start) + text.substring(matchResult.range.last + 1)).trim()
                    val canonical = locAliasMap[loc] ?: loc
                    return LocationResult(canonical, direction, remaining)
                }
            }
        }
    }

    // Fuzzy fallback for multi-char location names
    val multiCharLocs = allLocs.filter { it.length > 2 }
    if (multiCharLocs.isNotEmpty()) {
        val words = splitWords(text)
        for (i in words.indices) {
            val word = words[i].trim()
            if (word.length <= 2) continue
            val (match, _) = resolve(word, multiCharLocs, cutoff = 0.75)
            if (match != null) {
                val canonical = locAliasMap[match] ?: match
                val remaining = (words.subList(0, i) + words.subList(i + 1, words.size))
                    .joinToString(" ").trim()
                return LocationResult(canonical, "to", remaining)
            }
        }
    }

    return LocationResult(null, null, text)
}

private fun extractVerb(text: String, config: Map<String, Any?>): Pair<String?, String> {
    // Build verb map: candidate_text -> trans_type
    val verbMap = mutableMapOf<String, String>()
    val actionVerbs = config.stringListMap("action_verbs")
    for ((transType, verbs) in actionVerbs) {
        for (v in verbs) {
            verbMap[v] = transType
        }
    }
    val ttList = config.stringList("transaction_types")
    for (tt in ttList) {
        verbMap[tt] = tt
    }
    val aliases = config.stringMap("aliases")
    val ttSet = ttList.map { it.lowercase() }.toSet()
    for ((aliasKey, aliasTarget) in aliases) {
        if (aliasTarget.lowercase() in ttSet) {
            verbMap[aliasKey] = aliasTarget
        }
    }

    val allKeys = verbMap.keys.toList()

    // Stage 1: Word-boundary regex search (longest first, separator-normalized)
    for (key in allKeys.sortedByDescending { it.length }) {
        val pattern = boundaryPattern(key)
        val matchResult = Regex(pattern, RegexOption.IGNORE_CASE).find(text)
        if (matchResult != null) {
            val remaining = (text.substring(0, matchResult.range.first) +
                    text.substring(matchResult.range.last + 1)).trim()
            return verbMap[key]!! to remaining
        }
    }

    // Stage 2: Multi-word spans with separator normalization only
    val words = splitWords(text)
    val maxSpan = minOf(words.size, 3)
    for (spanLen in maxSpan downTo 2) {
        for (start in 0..words.size - spanLen) {
            val span = words.subList(start, start + spanLen).joinToString(" ").trim()
            if (span.length <= 2) continue
            val (match, mt) = resolve(span, allKeys, normalizeSeparators = true)
            if (match != null && mt in listOf("exact", "alias", "separator")) {
                val remaining = (words.subList(0, start) + words.subList(start + spanLen, words.size))
                    .joinToString(" ").trim()
                return verbMap[match]!! to remaining
            }
        }
    }

    // Stage 3: Single-word fuzzy fallback (handles misspellings)
    for (i in words.indices) {
        val w = words[i].trim()
        if (w.length <= 2) continue
        val (match, _) = resolve(w, allKeys, normalizeSeparators = true, cutoff = 0.75)
        if (match != null) {
            val remaining = (words.subList(0, i) + words.subList(i + 1, words.size))
                .joinToString(" ").trim()
            return verbMap[match]!! to remaining
        }
    }

    return null to text
}

private fun extractSupplierInfo(text: String, config: Map<String, Any?>): Pair<String?, String> {
    val allLocs = config.stringList("locations").map { it.lowercase() }.toMutableList()
    val defaultSource = (config["default_source"]?.toString() ?: "warehouse").lowercase()
    allLocs.add(defaultSource)
    val fromWords = config.stringList("from_words", listOf("from"))

    for (word in fromWords) {
        val pattern: Regex
        if (word.length <= 2 && !word.isAscii()) {
            pattern = Regex("${Regex.escape(word)}[\\-\\s]*(.+?)(?:\\s*$)", RegexOption.IGNORE_CASE)
        } else {
            pattern = Regex("\\b${Regex.escape(word)}\\s+(.+?)(?:\\s*$)", RegexOption.IGNORE_CASE)
        }
        val matchResult = pattern.find(text)
        if (matchResult != null) {
            val supplier = matchResult.groupValues[1].trim()
            if (supplier.lowercase() !in allLocs) {
                val remaining = text.substring(0, matchResult.range.first).trim()
                return supplier to remaining
            }
        }
    }
    return null to text
}

private data class QtyResult(val qty: Number?, val container: String?, val remaining: String)

private fun extractQty(text: String, config: Map<String, Any?>): QtyResult {
    var remaining = text

    // "half a [container]"
    val hm = Regex("\\bhalf\\s+a\\s+", RegexOption.IGNORE_CASE).find(remaining)
    if (hm != null) {
        val after = remaining.substring(hm.range.last + 1)
        val (cont, afterCont) = extractContainer(after, config)
        if (cont != null) {
            val before = remaining.substring(0, hm.range.first)
            remaining = ("$before $afterCont").trim()
            return QtyResult(0.5, cont, remaining)
        }
    }

    // Math expressions: 2x17, 2x 17, 11*920
    val mm = Regex("\\b(\\d+)\\s*[x\u00d7*]\\s*(\\d+)\\b").find(remaining)
    if (mm != null) {
        val qty = mm.groupValues[1].toInt() * mm.groupValues[2].toInt()
        remaining = (remaining.substring(0, mm.range.first) + remaining.substring(mm.range.last + 1)).trim()
        val (cont, afterCont) = extractContainer(remaining, config)
        return QtyResult(qty, cont, afterCont)
    }

    // Plain number
    val nm = Regex("\\b(\\d+)\\b").find(remaining)
    if (nm != null) {
        val qty = nm.groupValues[1].toInt()
        remaining = (remaining.substring(0, nm.range.first) + remaining.substring(nm.range.last + 1)).trim()
        val (cont, afterCont) = extractContainer(remaining, config)
        return QtyResult(qty, cont, afterCont)
    }

    // No number found — still try to extract a container (e.g. "קופסה שרי" = "a box of cherry tomatoes")
    // If a container is found, default qty to 1
    val (cont, afterCont) = extractContainer(remaining, config)
    if (cont != null) {
        return QtyResult(1, cont, afterCont)
    }

    return QtyResult(null, null, text)
}

private fun extractContainer(text: String, config: Map<String, Any?>): Pair<String?, String> {
    val containers = getAllContainers(config).toMutableSet()

    // Expand with container aliases
    val aliases = config.stringMap("aliases")
    val contLowerSet = containers.map { it.lowercase() }.toSet()
    val contAliasMap = mutableMapOf<String, String>()
    for ((aliasKey, aliasTarget) in aliases) {
        if (aliasTarget.lowercase() in contLowerSet) {
            contAliasMap[aliasKey] = aliasTarget
            containers.add(aliasKey)
        }
    }

    for (cont in containers.sortedByDescending { it.length }) {
        val canonical = contAliasMap[cont] ?: cont
        for (variant in containerVariants(cont)) {
            // Try anchored first (container right after number)
            val anchoredMatch = Regex("${Regex.escape(variant)}\\b", RegexOption.IGNORE_CASE)
                .matchAt(text.trim(), 0)
            if (anchoredMatch != null) {
                val remaining = text.trim().substring(anchoredMatch.range.last + 1).trim()
                return canonical to remaining
            }
            // Then anywhere in text
            val searchMatch = Regex("\\b${Regex.escape(variant)}\\b", RegexOption.IGNORE_CASE).find(text)
            if (searchMatch != null) {
                val remaining = (text.substring(0, searchMatch.range.first) +
                        text.substring(searchMatch.range.last + 1)).trim()
                return canonical to remaining
            }
        }
    }
    return null to text
}

/**
 * Get all container names from unit_conversions config.
 */
fun getAllContainers(config: Map<String, Any?>): Set<String> {
    val containers = mutableSetOf<String>()
    val conversions = config.unitConversionsMap()
    for ((_, convs) in conversions) {
        for (key in convs.keys) {
            if (key != "base_unit") {
                containers.add(key)
            }
        }
    }
    return containers
}

private fun containerVariants(container: String): List<String> {
    val words = container.split(" ")
    val last = words.last()
    val variants = mutableListOf(container)
    // Only apply English pluralization rules to ASCII words
    if (last.isAscii()) {
        val pluralized = if (last.endsWith("x") || last.endsWith("s") ||
            last.endsWith("sh") || last.endsWith("ch")
        ) {
            last + "es"
        } else {
            last + "s"
        }
        variants.add((words.dropLast(1) + listOf(pluralized)).joinToString(" ").trim())
    }
    return variants
}

private fun convertContainer(item: String, container: String, qty: Number, config: Map<String, Any?>): Number? {
    val conversions = config.unitConversionsMap()
    val convs = conversions[item] ?: return null
    val factor = convs[container] ?: return null
    // Multiply qty by factor, preserving integer types when possible
    val result = qty.toDouble() * factor.toDouble()
    return if (result == result.toLong().toDouble()) result.toInt() else result
}

private fun removeFiller(text: String, config: Map<String, Any?>?): String {
    val filler = if (config != null) {
        config.stringList("filler_words", DEFAULT_FILLER)
    } else {
        DEFAULT_FILLER
    }
    var result = text
    for (pattern in filler) {
        val regexPattern = if (!pattern.startsWith("\\")) {
            "\\b${Regex.escape(pattern)}\\b"
        } else {
            pattern
        }
        result = Regex(regexPattern, RegexOption.IGNORE_CASE).replace(result, "")
    }
    return Regex("\\s+").replace(result, " ").trim()
}

// ============================================================
// Item matching
// ============================================================

private fun matchItem(text: String, config: Map<String, Any?>): Pair<String?, String?> {
    val textClean = text.trim()
    if (textClean.isEmpty()) return null to null
    val textLower = textClean.lowercase()

    val items = config.stringList("items")
    val aliases = config.stringMap("aliases")

    // 1. Exact substring match against canonical items (longest first)
    for (item in items.sortedByDescending { it.length }) {
        if (item.lowercase() in textLower) {
            return item to item
        }
    }

    // 2. Exact substring match against aliases (longest first)
    for (alias in aliases.keys.sortedByDescending { it.length }) {
        if (alias.lowercase() in textLower) {
            return aliases[alias]!! to alias
        }
    }

    // 3. Whole text: plural, prefix, then fuzzy (via unified resolver)
    val (match, _) = resolve(
        textClean, items, aliases,
        tryPlural = true, tryPrefix = true, cutoff = 0.6
    )
    if (match != null) return match to textClean

    // 4. Word spans (longest to shortest)
    val words = textLower.split(" ").filter { it.isNotEmpty() }
    for (spanLen in minOf(words.size, 4) downTo 1) {
        for (start in 0..words.size - spanLen) {
            val span = words.subList(start, start + spanLen).joinToString(" ")
            val (spanMatch, _) = resolve(span, items, aliases, cutoff = 0.6)
            if (spanMatch != null) return spanMatch to span
        }
    }

    return null to null
}

// ============================================================
// Line merging
// ============================================================

private fun mergeLines(
    parsed: List<MutableMap<String, Any?>>,
    config: Map<String, Any?>
): List<MutableMap<String, Any?>> {
    if (parsed.isEmpty()) return emptyList()

    val merged = mutableListOf<MutableMap<String, Any?>>()
    var i = 0
    while (i < parsed.size) {
        val current = parsed[i]

        // Qty without item + next has item without qty -> merge
        // But not if the qty line had text that failed item matching
        if (current["has_qty"] == true && current["has_item"] == false
            && current["_unmatched_text"] == null
            && i + 1 < parsed.size
        ) {
            val nxt = parsed[i + 1]
            if (nxt["has_item"] == true && nxt["has_qty"] == false) {
                val combined = current.toMutableMap()
                combined["item"] = nxt["item"]
                combined["item_raw"] = nxt["item_raw"]
                combined["has_item"] = true
                combined["raw"] = "${current["raw"]}\n${nxt["raw"]}"
                // Apply container conversion now that we have both
                if (combined["container"] != null && combined["item"] != null) {
                    val conv = convertContainer(
                        combined["item"] as String,
                        combined["container"] as String,
                        combined["qty"] as Number,
                        config
                    )
                    if (conv != null) {
                        combined["qty"] = conv
                        combined["container"] = null
                    }
                }
                merged.add(combined)
                i += 2
                continue
            }
        }

        // Context-only line (verb/notes but no item/qty) -> apply to previous
        if (current["has_qty"] == false && current["has_item"] == false
            && (current["trans_type"] != null || current["notes_extra"] != null)
            && current["location"] == null // not a header with location
            && merged.isNotEmpty()
        ) {
            val prev = merged.last()
            if (current["trans_type"] != null && prev["trans_type"] == null) {
                prev["trans_type"] = current["trans_type"]
            }
            if (current["notes_extra"] != null) {
                prev["notes_extra"] = current["notes_extra"]
            }
            i += 1
            continue
        }

        merged.add(current)
        i += 1
    }

    return merged
}

// ============================================================
// Context broadcasting
// ============================================================

private fun broadcastContext(items: List<MutableMap<String, Any?>>) {
    if (items.isEmpty()) return

    // Forward pass
    var ctxLoc: String? = null
    var ctxDir: String? = null
    var ctxType: String? = null
    var ctxDate: LocalDate? = null
    for (item in items) {
        if (item["location"] != null) {
            ctxLoc = item["location"] as String
            ctxDir = item["direction"] as? String
        }
        if (item["trans_type"] != null) {
            ctxType = item["trans_type"] as String
        }
        if (item["date"] != null) {
            ctxDate = item["date"] as LocalDate
        }

        if (item["location"] == null && ctxLoc != null) {
            item["location"] = ctxLoc
            item["direction"] = ctxDir
        }
        if (item["trans_type"] == null && ctxType != null) {
            item["trans_type"] = ctxType
        }
        if (item["date"] == null && ctxDate != null) {
            item["date"] = ctxDate
        }
    }

    // Backward fill: find last-seen values from anywhere
    var lastLoc: String? = null
    var lastDir: String? = null
    var lastType: String? = null
    var lastDate: LocalDate? = null
    for (item in items) {
        if (item["location"] != null) {
            lastLoc = item["location"] as String
            lastDir = item["direction"] as? String
        }
        if (item["date"] != null) {
            lastDate = item["date"] as LocalDate
        }
        if (item["trans_type"] != null) {
            lastType = item["trans_type"] as String
        }
    }

    for (item in items) {
        if (item["location"] == null && lastLoc != null) {
            item["location"] = lastLoc
            item["direction"] = lastDir
        }
        if (item["date"] == null && lastDate != null) {
            item["date"] = lastDate
        }
        if (item["trans_type"] == null && lastType != null) {
            item["trans_type"] = lastType
        }
    }
}

// ============================================================
// Result generation
// ============================================================

private fun generateResult(
    items: List<MutableMap<String, Any?>>,
    config: Map<String, Any?>,
    today: LocalDate
): ParseResult {
    val rows = mutableListOf<Map<String, Any?>>()
    val notes = mutableListOf<String>()
    val unparseable = mutableListOf<String>()
    val transactionItems = mutableListOf<MutableMap<String, Any?>>()

    for (item in items) {
        if (item["has_item"] == true) {
            transactionItems.add(item)
        } else if (item["has_qty"] == true && item["has_item"] == false) {
            unparseable.add(item["raw"] as String)
        } else if (
            (item["trans_type"] != null && (item["location"] != null || item["date"] != null))
            || (item["location"] != null && item["date"] != null)
            || (item["location"] != null && item["_unmatched_text"] == null)
        ) {
            // Context-setting line -- skip
        } else {
            if (isNote(item)) {
                notes.add(item["raw"] as String)
            } else {
                unparseable.add(item["raw"] as String)
            }
        }
    }

    assignBatches(transactionItems)

    for (item in transactionItems) {
        val itemRows = itemToRows(item, config, today)
        rows.addAll(itemRows)
    }

    return ParseResult(rows = rows, notes = notes, unparseable = unparseable)
}

private fun isNote(item: Map<String, Any?>): Boolean {
    val raw = item["raw"] as? String ?: return false
    if (raw.isEmpty()) return false
    // Count alphabetic characters (Latin + Hebrew range)
    val alpha = raw.count { c ->
        c in 'a'..'z' || c in 'A'..'Z' || c.code in 0x0590..0x05FF
    }
    if (alpha == 0) return false
    return alpha.toDouble() / raw.length > 0.3
}

private fun assignBatches(items: List<MutableMap<String, Any?>>) {
    if (items.isEmpty()) return
    var batch = 1
    var prevDest = items[0]["location"]
    var prevDate = items[0]["date"]
    items[0]["batch"] = batch

    for (item in items.subList(1, items.size)) {
        val dest = item["location"]
        val dt = item["date"]
        if (dest != null && prevDest != null && dest != prevDest) {
            batch += 1
        } else if (dt != null && prevDate != null && dt != prevDate) {
            batch += 1
        }
        item["batch"] = batch
        if (dest != null) prevDest = dest
        if (dt != null) prevDate = dt
    }
}

private fun itemToRows(
    item: MutableMap<String, Any?>,
    config: Map<String, Any?>,
    today: LocalDate
): List<Map<String, Any?>> {
    val dt = (item["date"] as? LocalDate) ?: today
    val invType = (item["item"] as? String) ?: "???"
    val qty: Number = (item["qty"] as? Number) ?: 1
    var transType = item["trans_type"] as? String
    val location = item["location"] as? String
    val batch = (item["batch"] as? Number)?.toInt() ?: 1
    val notes = item["notes_extra"] as? String
    val defaultSource = config["default_source"]?.toString() ?: "warehouse"

    val rowBase = mutableMapOf<String, Any?>(
        "date" to dt, "inv_type" to invType, "batch" to batch, "notes" to notes,
    )

    // Preserve unconverted container info for TUI learning prompt
    if (item["container"] != null) {
        rowBase["_container"] = item["container"]
        rowBase["_raw_qty"] = qty
    }

    // Non-zero-sum -> single row
    val nonZeroSum = config.stringList(
        "non_zero_sum_types",
        NON_ZERO_SUM_DEFAULT.toList()
    ).toSet()
    if (transType in nonZeroSum) {
        return listOf(
            rowBase + mapOf(
                "qty" to qty,
                "trans_type" to transType,
                "vehicle_sub_unit" to (location ?: defaultSource),
            )
        )
    }

    // Transfer to a different location -> double-entry
    if (location != null && location != defaultSource) {
        if (transType == null) {
            transType = config["default_transfer_type"]?.toString() ?: "warehouse_to_branch"
        }
        val direction = item["direction"] as? String ?: "to"
        if (direction == "from") {
            // "from X" -> stock leaves X, arrives at warehouse
            return listOf(
                rowBase + mapOf(
                    "qty" to negAbs(qty),
                    "trans_type" to transType,
                    "vehicle_sub_unit" to location,
                ),
                rowBase + mapOf(
                    "qty" to posAbs(qty),
                    "trans_type" to transType,
                    "vehicle_sub_unit" to defaultSource,
                ),
            )
        }
        return listOf(
            rowBase + mapOf(
                "qty" to negAbs(qty),
                "trans_type" to transType,
                "vehicle_sub_unit" to defaultSource,
            ),
            rowBase + mapOf(
                "qty" to posAbs(qty),
                "trans_type" to transType,
                "vehicle_sub_unit" to location,
            ),
        )
    }

    // Receiving at warehouse -> single positive row
    if (location != null && location == defaultSource) {
        return listOf(
            rowBase + mapOf(
                "qty" to posAbs(qty),
                "trans_type" to transType,
                "vehicle_sub_unit" to defaultSource,
            )
        )
    }

    // No location -> single row with unknowns
    return listOf(
        rowBase + mapOf(
            "qty" to qty,
            "trans_type" to transType,
            "vehicle_sub_unit" to null,
        )
    )
}

// ============================================================
// Numeric helpers
// ============================================================

/**
 * Return -abs(n), preserving numeric type.
 */
private fun negAbs(n: Number): Number {
    val d = n.toDouble()
    val result = -kotlin.math.abs(d)
    return if (result == result.toLong().toDouble()) result.toInt() else result
}

/**
 * Return abs(n), preserving numeric type.
 */
private fun posAbs(n: Number): Number {
    val d = n.toDouble()
    val result = kotlin.math.abs(d)
    return if (result == result.toLong().toDouble()) result.toInt() else result
}
