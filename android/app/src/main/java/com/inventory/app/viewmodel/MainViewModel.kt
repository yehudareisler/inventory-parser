package com.inventory.app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.inventory.app.data.ConfigRepository
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
}
