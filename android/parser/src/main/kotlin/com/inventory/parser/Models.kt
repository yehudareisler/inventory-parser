package com.inventory.parser

import java.time.LocalDate

data class ParserConfig(
    val items: List<String> = emptyList(),
    val aliases: Map<String, String> = emptyMap(),
    val locations: List<String> = emptyList(),
    val defaultSource: String = "warehouse",
    val transactionTypes: List<String> = emptyList(),
    val actionVerbs: Map<String, List<String>> = emptyMap(),
    val unitConversions: Map<String, Map<String, Number>> = emptyMap(),
    val prepositions: Map<String, List<String>> = mapOf(
        "to" to listOf("to", "into"),
        "by" to listOf("by"),
        "from" to listOf("from"),
    ),
    val fromWords: List<String> = listOf("from"),
    val fillerWords: List<String> = listOf("\\bthat's\\b", "\\bwhat\\b", "\\bthe\\b", "\\bof\\b", "\\ba\\b", "\\ban\\b", "\\bsome\\b", "\\bvia\\b"),
    val nonZeroSumTypes: List<String> = listOf("eaten", "starting_point", "recount", "supplier_to_warehouse"),
    val defaultTransferType: String = "warehouse_to_branch",
)

data class ParseResult(
    val rows: List<Map<String, Any?>> = emptyList(),
    val notes: List<String> = emptyList(),
    val unparseable: List<String> = emptyList(),
)
