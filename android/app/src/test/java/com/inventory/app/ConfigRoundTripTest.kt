package com.inventory.app

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.inventory.parser.parse
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

/**
 * Verify that config (especially unit_conversions) survives the Gson round-trip
 * that happens in ConfigRepository (save → load from DataStore).
 *
 * Run with: ./gradlew :app:testDebugUnitTest
 */
class ConfigRoundTripTest {

    private val gson = Gson()

    private val hebrewConfig = mapOf(
        "items" to listOf("עגבניות שרי", "מלפפונים", "תפוחי אדמה קטנים", "ספגטי"),
        "aliases" to mapOf(
            "שרי" to "עגבניות שרי",
            "תפוח אדמה" to "תפוחי אדמה קטנים",
            "נודלס ספגטי" to "ספגטי",
        ),
        "locations" to listOf("ל", "כ", "נ"),
        "default_source" to "מחסן",
        "transaction_types" to listOf("נאכל", "מחסן_לסניף", "ספק_למחסן"),
        "action_verbs" to mapOf(
            "מחסן_לסניף" to listOf("העביר", "העבירו", "נתן", "שלח"),
            "ספק_למחסן" to listOf("קיבל", "קיבלו"),
            "נאכל" to listOf("נאכל", "נאכלו", "אכל"),
        ),
        "unit_conversions" to mapOf(
            "עגבניות שרי" to mapOf(
                "base_unit" to "יחידה",
                "קופסה קטנה" to 990,
                "קופסה" to 1980,
            ),
            "תפוחי אדמה קטנים" to mapOf(
                "base_unit" to "יחידה",
                "קופסה" to 920,
            ),
        ),
        "prepositions" to mapOf("to" to listOf("ל"), "by" to listOf("ב"), "from" to listOf("מ")),
        "from_words" to listOf("מאת"),
        "filler_words" to emptyList<String>(),
        "non_zero_sum_types" to listOf("נאכל", "נקודת_התחלה", "ספירה_חוזרת", "ספק_למחסן"),
        "default_transfer_type" to "מחסן_לסניף",
    )

    private fun roundTrip(config: Map<String, Any?>): Map<String, Any?> {
        val json = gson.toJson(config)
        val type = object : TypeToken<Map<String, Any?>>() {}.type
        return gson.fromJson(json, type)
    }

    @Test
    fun `unit_conversions survive Gson round-trip`() {
        val config = roundTrip(hebrewConfig)

        @Suppress("UNCHECKED_CAST")
        val conversions = config["unit_conversions"] as? Map<String, Any?>
        assertNotNull("unit_conversions should survive round-trip", conversions)

        @Suppress("UNCHECKED_CAST")
        val cherry = conversions!!["עגבניות שרי"] as? Map<String, Any?>
        assertNotNull("cherry tomato conversions should survive", cherry)

        val smallBoxFactor = cherry!!["קופסה קטנה"]
        assertNotNull("small box factor should exist", smallBoxFactor)
        assertEquals(990.0, (smallBoxFactor as Number).toDouble(), 0.001)

        val boxFactor = cherry["קופסה"]
        assertNotNull("box factor should exist", boxFactor)
        assertEquals(1980.0, (boxFactor as Number).toDouble(), 0.001)
    }

    @Test
    fun `parser applies small box conversion after Gson round-trip`() {
        val config = roundTrip(hebrewConfig)

        // "eaten by L, 2 small boxes of cherry tomatoes" → qty = 2 × 990 = 1980
        val input = "נאכל ב-ל 15.3.25\n2 קופסה קטנה עגבניות שרי"
        val result = parse(input, config, LocalDate.of(2025, 3, 19))

        assertEquals("Should produce 1 row (eaten = non-zero-sum)", 1, result.rows.size)
        val qty = (result.rows[0]["qty"] as Number).toInt()
        assertEquals("Qty should be 1980 (2 × 990)", 1980, qty)
    }

    @Test
    fun `parser applies box conversion for potatoes after Gson round-trip`() {
        val config = roundTrip(hebrewConfig)

        // "8 boxes small potatoes to כ" → 8 × 920 = 7360, double entry
        val input = "8 קופסה תפוחי אדמה קטנים ל-כ"
        val result = parse(input, config, LocalDate.of(2025, 3, 19))

        assertEquals("Should produce 2 rows (double entry)", 2, result.rows.size)
        val negQty = (result.rows[0]["qty"] as Number).toInt()
        assertEquals("Negative qty should be -7360", -7360, negQty)
        val posQty = (result.rows[1]["qty"] as Number).toInt()
        assertEquals("Positive qty should be 7360", 7360, posQty)
    }

    @Test
    fun `parser applies transfer with math after Gson round-trip`() {
        val config = roundTrip(hebrewConfig)

        val input = "העבירו 2x17 נודלס ספגטי ל-ל"
        val result = parse(input, config, LocalDate.of(2025, 3, 19))

        assertEquals("Should produce 2 rows (double entry)", 2, result.rows.size)
        val negQty = (result.rows[0]["qty"] as Number).toInt()
        assertEquals("Negative qty should be -34", -34, negQty)
        val posQty = (result.rows[1]["qty"] as Number).toInt()
        assertEquals("Positive qty should be 34", 34, posQty)
    }

    @Test
    fun `action_verbs survive Gson round-trip`() {
        val config = roundTrip(hebrewConfig)

        @Suppress("UNCHECKED_CAST")
        val verbs = config["action_verbs"] as? Map<String, Any?>
        assertNotNull("action_verbs should survive round-trip", verbs)

        @Suppress("UNCHECKED_CAST")
        val transferVerbs = verbs!!["מחסן_לסניף"] as? List<String>
        assertNotNull("transfer verbs should survive", transferVerbs)
        assertTrue("should contain העביר", transferVerbs!!.contains("העביר"))
    }

    @Test
    fun `aliases survive Gson round-trip`() {
        val config = roundTrip(hebrewConfig)

        @Suppress("UNCHECKED_CAST")
        val aliases = config["aliases"] as? Map<String, String>
        assertNotNull("aliases should survive round-trip", aliases)
        assertEquals("שרי should map to עגבניות שרי", "עגבניות שרי", aliases!!["שרי"])
    }
}
