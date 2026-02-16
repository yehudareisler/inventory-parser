package com.inventory.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.inventory.app.ui.components.RowTable
import com.inventory.app.viewmodel.MainViewModel
import com.inventory.parser.*
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewScreen(
    viewModel: MainViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val config by viewModel.config.collectAsState()
    val ui by viewModel.uiStrings.collectAsState()

    // Cell editing dialog state
    var editingRow by remember { mutableIntStateOf(-1) }
    var editingField by remember { mutableStateOf("") }
    var editValue by remember { mutableStateOf("") }

    // Alias learning dialog
    var aliasIdx by remember { mutableIntStateOf(0) }
    var showAliasDialog by remember { mutableStateOf(false) }

    // Conversion learning dialog
    var convIdx by remember { mutableIntStateOf(0) }
    var showConvDialog by remember { mutableStateOf(false) }
    var convFactor by remember { mutableStateOf("") }

    // Snackbar
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    fun showSnackbar(message: String) {
        scope.launch {
            snackbarHostState.showSnackbar(message)
        }
    }

    // Confirm action: check learning, then write to sheet (or show status)
    fun doConfirm() {
        viewModel.checkLearningOpportunities()
        val s = viewModel.state.value
        if (s.aliasPrompts.isNotEmpty()) {
            aliasIdx = 0
            showAliasDialog = true
        } else if (s.conversionPrompts.isNotEmpty()) {
            convIdx = 0
            showConvDialog = true
        } else {
            viewModel.writeToSheet { success, message ->
                if (success) {
                    viewModel.resetAfterConfirm()
                    onBack()
                } else {
                    // Show what we parsed so the user can verify
                    scope.launch {
                        snackbarHostState.showSnackbar(
                            message = "Sheets: $message. ${s.rows.size} row(s) parsed OK.",
                            duration = SnackbarDuration.Long,
                        )
                    }
                }
            }
        }
    }

    // Called after all alias/conv dialogs finish
    fun finishConfirm() {
        viewModel.writeToSheet { success, message ->
            if (success) {
                viewModel.resetAfterConfirm()
                onBack()
            } else {
                scope.launch {
                    snackbarHostState.showSnackbar(
                        message = "Sheets: $message. ${viewModel.state.value.rows.size} row(s) parsed OK.",
                        duration = SnackbarDuration.Long,
                    )
                }
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Review (${state.rows.size} rows)") },
                navigationIcon = {
                    IconButton(onClick = {
                        viewModel.discard()
                        onBack()
                    }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.addRow() }) {
                        Icon(Icons.Default.Add, contentDescription = ui.s("review_add_row_btn"))
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            BottomAppBar {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    // Write to Sheet
                    Button(
                        onClick = { doConfirm() },
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(ui.s("sheet_btn"))
                    }

                    // Retry (re-edit) — preserves input text
                    OutlinedButton(
                        onClick = {
                            viewModel.retry()
                            onBack()
                        },
                    ) {
                        Text(ui.s("help_retry_desc").take(5))
                    }
                }
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
        ) {
            // Notes
            if (state.notes.isNotEmpty()) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(8.dp)
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        for (note in state.notes) {
                            Text(
                                "${ui.s("note_prefix")}: $note",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
            }

            // Unparseable
            if (state.unparseable.isNotEmpty()) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(8.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        for (line in state.unparseable) {
                            Text(
                                "${ui.s("unparseable_prefix")}: $line",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                            )
                        }
                    }
                }
            }

            // Row table
            if (state.rows.isNotEmpty()) {
                RowTable(
                    rows = state.rows,
                    config = config,
                    onCellClick = { rowIdx, field ->
                        editingRow = rowIdx
                        editingField = field
                        editValue = formatCell(state.rows[rowIdx], field)
                    },
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }

    // Cell edit dialog
    if (editingRow >= 0) {
        val closedFields = getClosedSetFields(config)
        val isClosedSet = editingField in closedFields

        if (isClosedSet) {
            val options = getClosedSetOptions(editingField, config)
            ClosedSetPickerDialog(
                field = editingField,
                fieldDisplayName = ui.fieldName(editingField),
                options = options,
                currentValue = formatCell(state.rows[editingRow], editingField),
                onSelect = { value ->
                    viewModel.updateCell(editingRow, editingField, value)
                    editingRow = -1
                },
                onDelete = {
                    viewModel.deleteRow(editingRow)
                    editingRow = -1
                },
                onDismiss = { editingRow = -1 },
            )
        } else {
            OpenFieldEditDialog(
                field = editingField,
                fieldDisplayName = ui.fieldName(editingField),
                currentValue = editValue,
                onValueChange = { editValue = it },
                onConfirm = {
                    val parsed: Any? = when (editingField) {
                        "qty" -> evalQty(editValue)
                        "date" -> parseEditDate(editValue)
                        "batch" -> editValue.toIntOrNull()
                        else -> editValue.ifBlank { null }
                    }
                    if (parsed != null || editingField == "notes") {
                        viewModel.updateCell(editingRow, editingField, parsed)
                    }
                    editingRow = -1
                },
                onDelete = {
                    viewModel.deleteRow(editingRow)
                    editingRow = -1
                },
                onDismiss = { editingRow = -1 },
            )
        }
    }

    // Alias learning dialog
    if (showAliasDialog && aliasIdx < state.aliasPrompts.size) {
        val (original, canonical) = state.aliasPrompts[aliasIdx]
        AlertDialog(
            onDismissRequest = { showAliasDialog = false },
            title = { Text("Save alias?") },
            text = { Text(ui.s("save_alias_prompt", "original" to original, "canonical" to canonical)) },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.saveAlias(original, canonical)
                    aliasIdx++
                    if (aliasIdx >= state.aliasPrompts.size) {
                        showAliasDialog = false
                        val s = viewModel.state.value
                        if (s.conversionPrompts.isNotEmpty()) {
                            convIdx = 0
                            showConvDialog = true
                        } else {
                            finishConfirm()
                        }
                    }
                }) { Text(ui.commands["yes"]?.uppercase() ?: "Y") }
            },
            dismissButton = {
                TextButton(onClick = {
                    aliasIdx++
                    if (aliasIdx >= state.aliasPrompts.size) {
                        showAliasDialog = false
                        val s = viewModel.state.value
                        if (s.conversionPrompts.isNotEmpty()) {
                            convIdx = 0
                            showConvDialog = true
                        } else {
                            finishConfirm()
                        }
                    }
                }) { Text(ui.commands["no"]?.uppercase() ?: "N") }
            },
        )
    }

    // Conversion learning dialog
    if (showConvDialog && convIdx < state.conversionPrompts.size) {
        val (item, container) = state.conversionPrompts[convIdx]
        AlertDialog(
            onDismissRequest = { showConvDialog = false },
            title = { Text("Save conversion?") },
            text = {
                Column {
                    Text(ui.s("save_conversion_prompt", "container" to container, "item" to item))
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(
                        value = convFactor,
                        onValueChange = { convFactor = it },
                        label = { Text("Factor") },
                        singleLine = true,
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val factor = convFactor.toIntOrNull()
                    if (factor != null) {
                        viewModel.saveConversion(item, container, factor)
                    }
                    convFactor = ""
                    convIdx++
                    if (convIdx >= state.conversionPrompts.size) {
                        showConvDialog = false
                        finishConfirm()
                    }
                }) { Text("Save") }
            },
            dismissButton = {
                TextButton(onClick = {
                    convFactor = ""
                    convIdx++
                    if (convIdx >= state.conversionPrompts.size) {
                        showConvDialog = false
                        finishConfirm()
                    }
                }) { Text("Skip") }
            },
        )
    }
}

@Composable
private fun ClosedSetPickerDialog(
    field: String,
    fieldDisplayName: String,
    options: List<String>,
    currentValue: String,
    onSelect: (String) -> Unit,
    onDelete: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(fieldDisplayName) },
        text = {
            Column {
                for (option in options) {
                    val isSelected = option == currentValue
                    TextButton(
                        onClick = { onSelect(option) },
                        modifier = Modifier.fillMaxWidth(),
                        colors = if (isSelected) {
                            ButtonDefaults.textButtonColors(
                                contentColor = MaterialTheme.colorScheme.primary
                            )
                        } else {
                            ButtonDefaults.textButtonColors()
                        }
                    ) {
                        Text(
                            if (isSelected) "$option \u2713" else option,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
        dismissButton = {
            TextButton(onClick = onDelete) {
                Text("Delete row", color = MaterialTheme.colorScheme.error)
            }
        },
    )
}

@Composable
private fun OpenFieldEditDialog(
    field: String,
    fieldDisplayName: String,
    currentValue: String,
    onValueChange: (String) -> Unit,
    onConfirm: () -> Unit,
    onDelete: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(fieldDisplayName) },
        text = {
            OutlinedTextField(
                value = currentValue,
                onValueChange = onValueChange,
                label = { Text(fieldDisplayName) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            TextButton(onClick = onConfirm) { Text("OK") }
        },
        dismissButton = {
            Row {
                TextButton(onClick = onDelete) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        },
    )
}
