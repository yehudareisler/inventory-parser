package com.inventory.parser

import java.time.LocalDate

/**
 * Configuration for the inventory parser.
 */
data class ParserConfig(
    val items: List<String> = emptyList(),
    val aliases: Map<String, String> = emptyMap(),
    val locations: List<String> = emptyList(),
    val defaultSource: String = "warehouse",
    val transactionTypes: List<String> = emptyList(),
    val actionVerbs: Map<String, List<String>> = emptyMap(),
    val unitConversions: Map<String, Map<String, Number>> = emptyMap(),
    val prepositions: Map<String, List<String>> = emptyMap(),
    val fromWords: List<String> = emptyList(),
    val fillerWords: List<String> = emptyList(),
    val nonZeroSumTypes: List<String> = emptyList(),
    val defaultTransferType: String = "warehouse_to_branch",
)

/**
 * A single parsed row (one side of a double-entry transaction).
 */
data class ParsedRow(
    val date: LocalDate? = null,
    val invType: String? = null,
    val qty: Int = 0,
    val transType: String? = null,
    val vehicleSubUnit: String? = null,
    val batch: Int = 1,
    val notes: String? = null,
    val container: String? = null,
    val rawQty: Int? = null,
)

/**
 * Result of parsing an inventory message.
 */
data class ParseResult(
    val rows: List<ParsedRow> = emptyList(),
    val notes: List<String> = emptyList(),
    val unparseable: List<String> = emptyList(),
)
