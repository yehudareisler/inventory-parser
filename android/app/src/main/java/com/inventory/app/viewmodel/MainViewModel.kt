package com.inventory.app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.inventory.app.data.ConfigRepository
import com.inventory.app.sheets.AuthManager
import com.inventory.app.sheets.SheetsRepository
import com.inventory.parser.*
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

data class ParseState(
    val inputText: String = "",
    val rows: List<MutableMap<String, Any?>> = emptyList(),
    val notes: List<String> = emptyList(),
    val unparseable: List<String> = emptyList(),
    val originalTokens: Map<Int, String> = emptyMap(),
    val isParsed: Boolean = false,
    val aliasPrompts: List<Pair<String, String>> = emptyList(),
    val conversionPrompts: List<Pair<String, String>> = emptyList(),
    val sheetWriteStatus: String? = null,
)

@HiltViewModel
class MainViewModel @Inject constructor(
    private val configRepository: ConfigRepository,
    private val sheetsRepository: SheetsRepository,
    val authManager: AuthManager,
) : ViewModel() {

    private val _state = MutableStateFlow(ParseState())
    val state: StateFlow<ParseState> = _state.asStateFlow()

    val config: StateFlow<Map<String, Any?>> = configRepository.configFlow
        .stateIn(viewModelScope, SharingStarted.Eagerly, emptyMap())

    val uiStrings: StateFlow<UiStrings> = config.map { UiStrings(it) }
        .stateIn(viewModelScope, SharingStarted.Eagerly, UiStrings(emptyMap()))

    fun updateInput(text: String) {
        _state.update { it.copy(inputText = text) }
    }

    fun parse() {
        val text = _state.value.inputText
        if (text.isBlank()) return

        val cfg = config.value
        val result = parse(text, cfg, LocalDate.now())

        // Collect original tokens for alias learning
        val tokens = mutableMapOf<Int, String>()
        for (i in result.rows.indices) {
            val origItem = result.rows[i]["_original_item"] as? String
            if (origItem != null) tokens[i] = origItem
        }

        // Convert rows to mutable maps
        val mutableRows = result.rows.map { it.toMutableMap() }

        _state.update {
            it.copy(
                rows = mutableRows,
                notes = result.notes,
                unparseable = result.unparseable,
                originalTokens = tokens,
                isParsed = true,
                aliasPrompts = emptyList(),
                conversionPrompts = emptyList(),
                sheetWriteStatus = null,
            )
        }
    }

    fun updateCell(rowIdx: Int, field: String, value: Any?) {
        val currentRows = _state.value.rows.toMutableList()
        if (rowIdx !in currentRows.indices) return

        currentRows[rowIdx][field] = value
        updatePartner(currentRows, rowIdx, field, value)

        _state.update { it.copy(rows = currentRows) }
    }

    fun deleteRow(rowIdx: Int) {
        val currentRows = _state.value.rows.toMutableList()
        if (rowIdx !in currentRows.indices) return
        currentRows.removeAt(rowIdx)
        _state.update { it.copy(rows = currentRows) }
    }

    fun addRow() {
        val currentRows = _state.value.rows.toMutableList()
        currentRows.add(emptyRow())
        _state.update { it.copy(rows = currentRows) }
    }

    fun checkLearningOpportunities() {
        val s = _state.value
        val cfg = config.value
        val aliasPrompts = checkAliasOpportunity(s.rows, s.originalTokens, cfg)
        val convPrompts = checkConversionOpportunity(s.rows, cfg)
        _state.update { it.copy(aliasPrompts = aliasPrompts, conversionPrompts = convPrompts) }
    }

    fun saveAlias(alias: String, target: String) {
        viewModelScope.launch {
            configRepository.addAlias(alias, target)
        }
    }

    fun saveConversion(item: String, container: String, factor: Number) {
        viewModelScope.launch {
            configRepository.addConversion(item, container, factor)
        }
    }

    fun discard() {
        _state.update { ParseState() }
    }

    fun resetAfterConfirm() {
        _state.update { ParseState() }
    }

    fun saveConfig(config: Map<String, Any?>) {
        viewModelScope.launch {
            configRepository.saveConfig(config)
        }
    }

    fun updateConfigField(key: String, value: Any?) {
        viewModelScope.launch {
            configRepository.updateConfig { it[key] = value }
        }
    }

    @Suppress("UNCHECKED_CAST")
    fun writeToSheet(onResult: (Boolean, String) -> Unit) {
        viewModelScope.launch {
            val token = authManager.authState.value.accessToken
            if (token == null) {
                onResult(false, "Not signed in")
                return@launch
            }
            val cfg = config.value
            val gs = cfg["google_sheets"] as? Map<String, Any?> ?: run {
                onResult(false, "No Google Sheets config")
                return@launch
            }
            val spreadsheetId = gs["spreadsheet_id"] as? String ?: run {
                onResult(false, "No spreadsheet ID configured")
                return@launch
            }
            val output = gs["output"] as? Map<String, Any?> ?: run {
                onResult(false, "No output config")
                return@launch
            }
            val txnOutput = output["transactions"] as? Map<String, String> ?: run {
                onResult(false, "No transaction output sheet configured")
                return@launch
            }
            val sheetName = txnOutput["sheet"] ?: run {
                onResult(false, "No output sheet name")
                return@launch
            }

            try {
                val count = sheetsRepository.appendRows(
                    accessToken = token,
                    spreadsheetId = spreadsheetId,
                    sheetName = sheetName,
                    rows = _state.value.rows,
                    config = cfg,
                )
                _state.update { it.copy(sheetWriteStatus = "$count row(s) written") }
                onResult(true, "$count row(s) written to sheet")
            } catch (e: Exception) {
                _state.update { it.copy(sheetWriteStatus = "Error: ${e.message}") }
                onResult(false, e.message ?: "Write failed")
            }
        }
    }

    @Suppress("UNCHECKED_CAST")
    fun loadSheetConfig() {
        viewModelScope.launch {
            val token = authManager.authState.value.accessToken ?: return@launch
            val cfg = config.value
            val gs = cfg["google_sheets"] as? Map<String, Any?> ?: return@launch
            val spreadsheetId = gs["spreadsheet_id"] as? String ?: return@launch
            val inputMappings = gs["input"] as? Map<String, Map<String, String>> ?: return@launch

            try {
                val overlay = sheetsRepository.loadSheetConfig(token, spreadsheetId, inputMappings)
                configRepository.updateConfig { current ->
                    current.putAll(overlay)
                }
            } catch (_: Exception) {
                // Silently fail — local config is still usable
            }
        }
    }
}
