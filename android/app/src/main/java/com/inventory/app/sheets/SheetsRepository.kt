package com.inventory.app.sheets

import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport
import com.google.api.client.json.gson.GsonFactory
import com.google.api.services.sheets.v4.Sheets
import com.google.api.services.sheets.v4.model.AppendValuesResponse
import com.google.api.services.sheets.v4.model.ValueRange
import com.google.auth.http.HttpCredentialsAdapter
import com.google.auth.oauth2.AccessToken
import com.google.auth.oauth2.GoogleCredentials
import com.inventory.parser.formatCell
import com.inventory.parser.getFieldOrder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Google Sheets reader/writer mirroring inventory_sheets.py.
 * All operations are suspend functions running on Dispatchers.IO.
 */
@Singleton
class SheetsRepository @Inject constructor() {

    private fun buildService(accessToken: String): Sheets {
        val credentials = GoogleCredentials.create(AccessToken(accessToken, null))
        val transport = GoogleNetHttpTransport.newTrustedTransport()
        val jsonFactory = GsonFactory.getDefaultInstance()
        return Sheets.Builder(transport, jsonFactory, HttpCredentialsAdapter(credentials))
            .setApplicationName("InventoryParser")
            .build()
    }

    // ============================================================
    // Readers
    // ============================================================

    suspend fun readSingleColumn(
        accessToken: String,
        spreadsheetId: String,
        sheetName: String,
        cellRange: String,
    ): List<String> = withContext(Dispatchers.IO) {
        val service = buildService(accessToken)
        val range = "$sheetName!$cellRange"
        val response = service.spreadsheets().values().get(spreadsheetId, range).execute()
        val values = response.getValues() ?: return@withContext emptyList()
        values.mapNotNull { row ->
            val cell = row.firstOrNull()?.toString()?.trim()
            if (!cell.isNullOrBlank()) cell else null
        }
    }

    suspend fun readKeyValueColumns(
        accessToken: String,
        spreadsheetId: String,
        sheetName: String,
        cellRange: String,
    ): Map<String, String> = withContext(Dispatchers.IO) {
        val service = buildService(accessToken)
        val range = "$sheetName!$cellRange"
        val response = service.spreadsheets().values().get(spreadsheetId, range).execute()
        val values = response.getValues() ?: return@withContext emptyMap()
        val result = mutableMapOf<String, String>()
        for (row in values) {
            if (row.size >= 2) {
                val key = row[0]?.toString()?.trim() ?: continue
                val value = row[1]?.toString()?.trim() ?: continue
                if (key.isNotBlank()) result[key] = value
            }
        }
        result
    }

    suspend fun readActionVerbs(
        accessToken: String,
        spreadsheetId: String,
        sheetName: String,
        cellRange: String,
    ): Map<String, List<String>> = withContext(Dispatchers.IO) {
        val service = buildService(accessToken)
        val range = "$sheetName!$cellRange"
        val response = service.spreadsheets().values().get(spreadsheetId, range).execute()
        val values = response.getValues() ?: return@withContext emptyMap()
        val result = mutableMapOf<String, List<String>>()
        for (row in values) {
            if (row.size >= 2) {
                val transType = row[0]?.toString()?.trim() ?: continue
                val verbs = row[1]?.toString()?.split(",")?.map { it.trim() }?.filter { it.isNotBlank() } ?: continue
                if (transType.isNotBlank()) result[transType] = verbs
            }
        }
        result
    }

    suspend fun readUnitConversions(
        accessToken: String,
        spreadsheetId: String,
        sheetName: String,
        cellRange: String,
    ): Map<String, Map<String, Number>> = withContext(Dispatchers.IO) {
        val service = buildService(accessToken)
        val range = "$sheetName!$cellRange"
        val response = service.spreadsheets().values().get(spreadsheetId, range).execute()
        val values = response.getValues() ?: return@withContext emptyMap()
        val result = mutableMapOf<String, MutableMap<String, Number>>()
        for (row in values) {
            if (row.size >= 3) {
                val item = row[0]?.toString()?.trim() ?: continue
                val container = row[1]?.toString()?.trim() ?: continue
                val factorStr = row[2]?.toString()?.trim() ?: continue
                if (item.isBlank()) continue
                val factor = try {
                    val d = factorStr.toDouble()
                    if (d == d.toLong().toDouble()) d.toLong().toInt() else d
                } catch (_: NumberFormatException) { continue }
                result.getOrPut(item) { mutableMapOf() }[container] = factor
            }
        }
        result
    }

    /**
     * Load all configured input ranges and return a map to overlay on config.
     * Mirrors load_sheet_config() from Python.
     */
    suspend fun loadSheetConfig(
        accessToken: String,
        spreadsheetId: String,
        inputMappings: Map<String, Map<String, String>>,
    ): Map<String, Any?> {
        val overlay = mutableMapOf<String, Any?>()
        for ((fieldName, mapping) in inputMappings) {
            val sheetName = mapping["sheet"] ?: continue
            val cellRange = mapping["range"] ?: continue

            overlay[fieldName] = when (fieldName) {
                "aliases" -> readKeyValueColumns(accessToken, spreadsheetId, sheetName, cellRange)
                "action_verbs" -> readActionVerbs(accessToken, spreadsheetId, sheetName, cellRange)
                "unit_conversions" -> readUnitConversions(accessToken, spreadsheetId, sheetName, cellRange)
                else -> readSingleColumn(accessToken, spreadsheetId, sheetName, cellRange)
            }
        }
        return overlay
    }

    // ============================================================
    // Writers
    // ============================================================

    suspend fun appendRows(
        accessToken: String,
        spreadsheetId: String,
        sheetName: String,
        rows: List<Map<String, Any?>>,
        config: Map<String, Any?>,
    ): Int = withContext(Dispatchers.IO) {
        if (rows.isEmpty()) return@withContext 0
        val service = buildService(accessToken)
        val fieldOrder = getFieldOrder(config)
        val values = rows.map { row ->
            fieldOrder.map { field -> formatCell(row, field) as Any }
        }
        val body = ValueRange().setValues(values)
        val range = "$sheetName!A1"
        service.spreadsheets().values()
            .append(spreadsheetId, range, body)
            .setValueInputOption("USER_ENTERED")
            .execute()
        rows.size
    }

    suspend fun appendAlias(
        accessToken: String,
        spreadsheetId: String,
        sheetName: String,
        alias: String,
        target: String,
    ) = withContext(Dispatchers.IO) {
        val service = buildService(accessToken)
        val body = ValueRange().setValues(listOf(listOf(alias, target)))
        val range = "$sheetName!A1"
        service.spreadsheets().values()
            .append(spreadsheetId, range, body)
            .setValueInputOption("USER_ENTERED")
            .execute()
    }

    suspend fun appendConversion(
        accessToken: String,
        spreadsheetId: String,
        sheetName: String,
        item: String,
        container: String,
        factor: Number,
    ) = withContext(Dispatchers.IO) {
        val service = buildService(accessToken)
        val body = ValueRange().setValues(listOf(listOf(item, container, factor)))
        val range = "$sheetName!A1"
        service.spreadsheets().values()
            .append(spreadsheetId, range, body)
            .setValueInputOption("USER_ENTERED")
            .execute()
    }
}
