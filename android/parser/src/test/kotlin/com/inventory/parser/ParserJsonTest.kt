package com.inventory.parser

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.Arguments
import org.junit.jupiter.params.provider.MethodSource
import java.io.InputStreamReader
import java.time.LocalDate
import kotlin.math.abs

/**
 * JSON-driven parser tests.
 *
 * Loads test cases from test_data/ (classpath resources) and runs them against
 * the Kotlin parser. Mirrors the Python test_parser_json.py to ensure parity.
 *
 * Usage:
 *     ./gradlew :parser:test --tests "com.inventory.parser.ParserJsonTest"
 */
class ParserJsonTest {

    companion object {
        private val gson = Gson()
        private val configCache = mutableMapOf<String, Map<String, Any?>>()

        // ============================================================
        // Resource loading
        // ============================================================

        private fun loadResource(path: String): String {
            val stream = ParserJsonTest::class.java.classLoader.getResourceAsStream(path)
                ?: error("Resource not found: $path")
            return InputStreamReader(stream, Charsets.UTF_8).use { it.readText() }
        }

        private fun parseJsonMap(json: String): Map<String, Any?> {
            val type = object : TypeToken<Map<String, Any?>>() {}.type
            return gson.fromJson(json, type)
        }

        private fun listResourceFiles(dirPath: String): List<String> {
            // List JSON files from the classpath resource directory.
            // Since classpath directories can't be listed portably, we scan
            // for known config files and case files by trying the directory.
            val url = ParserJsonTest::class.java.classLoader.getResource(dirPath)
                ?: error("Resource directory not found: $dirPath")
            val dir = java.io.File(url.toURI())
            return dir.listFiles()
                ?.filter { it.extension == "json" }
                ?.sorted()
                ?.map { "$dirPath/${it.name}" }
                ?: emptyList()
        }

        // ============================================================
        // Config loading
        // ============================================================

        private fun loadConfig(configId: String): Map<String, Any?> {
            configCache[configId]?.let { return deepCopyMap(it) }

            val json = loadResource("test_data/configs/$configId.json")
            val data = parseJsonMap(json).toMutableMap()

            val extendsId = data["extends"] as? String
            if (extendsId != null) {
                val base = loadConfig(extendsId).toMutableMap()
                for ((k, v) in data) {
                    if (k != "id" && k != "extends") {
                        base[k] = v
                    }
                }
                configCache[configId] = base
                return deepCopyMap(base)
            }

            configCache[configId] = data
            return deepCopyMap(data)
        }

        @Suppress("UNCHECKED_CAST")
        private fun deepCopyMap(map: Map<String, Any?>): MutableMap<String, Any?> {
            val copy = mutableMapOf<String, Any?>()
            for ((k, v) in map) {
                copy[k] = deepCopyValue(v)
            }
            return copy
        }

        private fun deepCopyValue(value: Any?): Any? {
            return when (value) {
                null -> null
                is Map<*, *> -> {
                    val copy = mutableMapOf<Any?, Any?>()
                    for ((k, v) in value) {
                        copy[k] = deepCopyValue(v)
                    }
                    copy
                }
                is List<*> -> value.map { deepCopyValue(it) }.toMutableList()
                else -> value // primitives (String, Number, Boolean) are immutable
            }
        }

        @Suppress("UNCHECKED_CAST")
        private fun applyOverrides(config: MutableMap<String, Any?>, overrides: Map<String, Any?>) {
            for ((key, value) in overrides) {
                when (key) {
                    "aliases_add" -> {
                        val existing = (config.getOrPut("aliases") { mutableMapOf<String, Any?>() }) as MutableMap<String, Any?>
                        existing.putAll(value as Map<String, Any?>)
                    }
                    "items_add" -> {
                        val existing = (config.getOrPut("items") { mutableListOf<Any?>() }) as MutableList<Any?>
                        existing.addAll(value as List<Any?>)
                    }
                    else -> {
                        config[key] = value
                    }
                }
            }
        }

        // ============================================================
        // Date handling
        // ============================================================

        private fun parseDateStr(s: Any?, today: LocalDate): LocalDate? {
            if (s == null) return null
            val str = s.toString()
            if (str == "TODAY") return today
            return LocalDate.parse(str)
        }

        private fun parseToday(group: Map<String, Any?>): LocalDate {
            val todayStr = group["today"] as? String ?: "2025-03-19"
            return LocalDate.parse(todayStr)
        }

        // ============================================================
        // Test collection
        // ============================================================

        @JvmStatic
        fun testCases(): List<Arguments> {
            val cases = mutableListOf<Arguments>()
            val caseFiles = listResourceFiles("test_data/cases/parser")

            for (filePath in caseFiles) {
                val json = loadResource(filePath)
                val group = parseJsonMap(json)
                val today = parseToday(group)
                val baseConfigId = group["config"] as? String

                @Suppress("UNCHECKED_CAST")
                val tests = group["tests"] as? List<Map<String, Any?>> ?: continue
                val groupName = group["group"] as? String
                    ?: filePath.substringAfterLast('/').removeSuffix(".json")

                for (test in tests) {
                    val testName = test["name"] as String
                    val testId = "$groupName::$testName"
                    cases.add(Arguments.of(testId, group, test, today, baseConfigId))
                }
            }
            return cases
        }
    }

    // ============================================================
    // Numeric comparison helpers
    // ============================================================

    /**
     * Loose numeric comparison: convert both sides to Double for comparison.
     * Gson deserializes all JSON numbers as Double. The parser may produce
     * Int or Double values.
     */
    private fun numbersEqual(actual: Number?, expected: Number?): Boolean {
        if (actual == null && expected == null) return true
        if (actual == null || expected == null) return false
        return actual.toDouble() == expected.toDouble()
    }

    /**
     * Compare an actual row value against an expected JSON value, taking into
     * account type differences (date strings, numeric types, nulls).
     */
    private fun valuesMatch(actual: Any?, expected: Any?, field: String, today: LocalDate): Boolean {
        if (field == "date") {
            val expectedDate = parseDateStr(expected, today)
            return actual == expectedDate
        }
        if (expected == null) return actual == null
        if (actual == null) return false
        if (expected is Number && actual is Number) {
            return numbersEqual(actual, expected)
        }
        return actual.toString() == expected.toString()
    }

    // ============================================================
    // Assertion helpers
    // ============================================================

    @Suppress("UNCHECKED_CAST")
    private fun checkRowFields(
        actualRow: Map<String, Any?>,
        expectedRow: Map<String, Any?>,
        today: LocalDate,
        testName: String,
        rowIdx: Int,
    ) {
        for ((field, expectedVal) in expectedRow) {
            val actualVal = actualRow[field]
            assertTrue(
                valuesMatch(actualVal, expectedVal, field, today),
                "$testName row[$rowIdx].$field: expected ${formatExpected(expectedVal, field, today)}, got $actualVal"
            )
        }
    }

    private fun formatExpected(value: Any?, field: String, today: LocalDate): String {
        if (field == "date") {
            return parseDateStr(value, today).toString()
        }
        return value.toString()
    }

    @Suppress("UNCHECKED_CAST")
    private fun runAssertions(
        assertions: Map<String, Any?>,
        rows: List<Map<String, Any?>>,
        notes: List<String>,
        unparseable: List<String>,
        testName: String,
        today: LocalDate,
    ) {
        for ((key, value) in assertions) {
            when (key) {
                "row_count" -> {
                    val expected = (value as Number).toInt()
                    assertEquals(expected, rows.size, "$testName: expected $expected rows, got ${rows.size}")
                }

                "row_count_gte" -> {
                    val expected = (value as Number).toInt()
                    assertTrue(rows.size >= expected, "$testName: expected >= $expected rows, got ${rows.size}")
                }

                "notes_count" -> {
                    val expected = (value as Number).toInt()
                    assertEquals(expected, notes.size, "$testName: expected $expected notes, got ${notes.size}")
                }

                "unparseable_count" -> {
                    val expected = (value as Number).toInt()
                    assertEquals(expected, unparseable.size, "$testName: expected $expected unparseable, got ${unparseable.size}")
                }

                "unparseable_count_gt" -> {
                    val expected = (value as Number).toInt()
                    assertTrue(unparseable.size > expected, "$testName: expected > $expected unparseable, got ${unparseable.size}")
                }

                "batch_sum_zero" -> {
                    val batchNums = value as List<*>
                    val batchSums = mutableMapOf<Int, Double>()
                    for (row in rows) {
                        val b = (row["batch"] as Number).toInt()
                        val qty = (row["qty"] as Number).toDouble()
                        batchSums[b] = (batchSums[b] ?: 0.0) + qty
                    }
                    for (batchNum in batchNums) {
                        val bn = (batchNum as Number).toInt()
                        val sum = batchSums[bn] ?: 0.0
                        assertEquals(0.0, sum, "$testName: batch $bn sums to $sum, expected 0")
                    }
                }

                "field_contains" -> {
                    val checks = value as Map<String, Any?>
                    for ((path, substr) in checks) {
                        val (rowIdxStr, field) = path.split('.', limit = 2)
                        val rowIdx = rowIdxStr.toInt()
                        val actual = rows[rowIdx][field]?.toString() ?: ""
                        val substrStr = substr.toString()
                        assertTrue(
                            substrStr in actual,
                            "$testName: row[$rowIdx].$field should contain '$substrStr', got '$actual'"
                        )
                    }
                }

                "notes_contains" -> {
                    val checks = value as Map<String, Any?>
                    for ((idxStr, substr) in checks) {
                        val idx = idxStr.toInt()
                        val substrStr = substr.toString()
                        assertTrue(
                            substrStr in notes[idx],
                            "$testName: notes[$idx] should contain '$substrStr'"
                        )
                    }
                }

                "all_rows_have" -> {
                    val fieldChecks = value as Map<String, Any?>
                    for ((field, expectedVal) in fieldChecks) {
                        for ((i, row) in rows.withIndex()) {
                            val actual = row[field]
                            assertTrue(
                                valuesMatch(actual, expectedVal, field, today),
                                "$testName: row[$i].$field: expected ${formatExpected(expectedVal, field, today)}, got $actual"
                            )
                        }
                    }
                }

                "any_row_has" -> {
                    val fieldChecks = value as Map<String, Any?>
                    val found = rows.any { row ->
                        fieldChecks.all { (f, v) -> valuesMatch(row[f], v, f, today) }
                    }
                    assertTrue(found, "$testName: no row matches $value")
                }

                "field_not_equal" -> {
                    val checks = value as Map<String, Any?>
                    for ((path, forbiddenVal) in checks) {
                        val (rowIdxStr, field) = path.split('.', limit = 2)
                        val rowIdx = rowIdxStr.toInt()
                        val actual = rows[rowIdx][field]
                        assertFalse(
                            valuesMatch(actual, forbiddenVal, field, today),
                            "$testName: row[$rowIdx].$field should NOT be $forbiddenVal"
                        )
                    }
                }

                "abs_qty" -> {
                    val checks = value as Map<String, Any?>
                    for ((idxStr, expectedAbs) in checks) {
                        val idx = idxStr.toInt()
                        val actualQty = (rows[idx]["qty"] as Number).toDouble()
                        val expectedAbsVal = (expectedAbs as Number).toDouble()
                        assertEquals(
                            expectedAbsVal, abs(actualQty),
                            "$testName: abs(row[$idx].qty): expected $expectedAbsVal, got ${abs(actualQty)}"
                        )
                    }
                }

                "qty_gt" -> {
                    val checks = value as Map<String, Any?>
                    for ((idxStr, threshold) in checks) {
                        val idx = idxStr.toInt()
                        val actualQty = (rows[idx]["qty"] as Number).toDouble()
                        val thresholdVal = (threshold as Number).toDouble()
                        assertTrue(
                            actualQty > thresholdVal,
                            "$testName: row[$idx].qty should be > $thresholdVal, got $actualQty"
                        )
                    }
                }

                "no_unparseable_contains" -> {
                    val forbidden = value.toString()
                    for (text in unparseable) {
                        assertFalse(
                            forbidden in text,
                            "$testName: unparseable should not contain '$forbidden'"
                        )
                    }
                }

                "unparseable_contains" -> {
                    val checks = value as Map<String, Any?>
                    for ((idxStr, substr) in checks) {
                        val idx = idxStr.toInt()
                        val substrStr = substr.toString()
                        assertTrue(
                            substrStr in unparseable[idx],
                            "$testName: unparseable[$idx] should contain '$substrStr', got '${unparseable[idx]}'"
                        )
                    }
                }

                else -> {
                    fail<Unit>("Unknown assertion type: $key")
                }
            }
        }
    }

    // ============================================================
    // Test runner
    // ============================================================

    @ParameterizedTest(name = "{0}")
    @MethodSource("testCases")
    @Suppress("UNCHECKED_CAST")
    fun testJson(
        testId: String,
        group: Map<String, Any?>,
        testCase: Map<String, Any?>,
        today: LocalDate,
        baseConfigId: String?,
    ) {
        val testName = testCase["name"] as String
        val function = testCase["function"] as? String ?: "parse"

        // --- fuzzy_resolve tests ---
        if (function == "fuzzy_resolve") {
            val fi = testCase["fuzzy_input"] as Map<String, Any?>
            val text = fi["text"] as String
            val items = fi["items"] as List<String>
            val aliases = fi["aliases"] as? Map<String, String> ?: emptyMap()

            val (result, matchType) = fuzzyResolve(text, items, aliases)

            val ef = testCase["expected_fuzzy"] as Map<String, Any?>
            val expectedResult = ef["result"] as? String
            val expectedMatchType = ef["match_type"] as? String

            assertEquals(expectedResult, result, "$testName: fuzzy result expected '$expectedResult', got '$result'")
            assertEquals(expectedMatchType, matchType, "$testName: match_type expected '$expectedMatchType', got '$matchType'")
            return
        }

        // --- parse tests ---
        // Build config
        val config: MutableMap<String, Any?> = if (testCase.containsKey("config_inline")) {
            val inline = testCase["config_inline"] as? Map<String, Any?>
            if (inline != null) deepCopyMap(inline) else mutableMapOf()
        } else {
            val configId = testCase["config"] as? String ?: baseConfigId
                ?: error("$testName: no config_id found")
            loadConfig(configId).toMutableMap()
        }

        val overrides = testCase["config_overrides"] as? Map<String, Any?> ?: emptyMap()
        if (overrides.isNotEmpty()) {
            applyOverrides(config, overrides)
        }

        // Parse
        val result = parse(testCase["input"] as String, config, today)
        val rows = result.rows
        val notes = result.notes
        val unparseable = result.unparseable

        // Check expected_rows (partial field matching)
        val expectedRows = testCase["expected_rows"] as? List<Map<String, Any?>> ?: emptyList()
        for ((i, expectedRow) in expectedRows.withIndex()) {
            assertTrue(
                i < rows.size,
                "$testName: expected row[$i] but only ${rows.size} rows"
            )
            checkRowFields(rows[i], expectedRow, today, testName, i)
        }

        // Check expected_notes
        val expectedNotes = testCase["expected_notes"] as? List<String>
        if (expectedNotes != null && expectedNotes.isNotEmpty()) {
            assertEquals(expectedNotes, notes, "$testName: notes mismatch")
        }

        // Check expected_unparseable
        val expectedUnp = testCase["expected_unparseable"] as? List<String>
        if (expectedUnp != null && expectedUnp.isNotEmpty()) {
            assertEquals(expectedUnp, unparseable, "$testName: unparseable mismatch")
        }

        // Run assertions
        val assertions = testCase["assertions"] as? Map<String, Any?> ?: emptyMap()
        runAssertions(assertions, rows, notes, unparseable, testName, today)
    }
}
