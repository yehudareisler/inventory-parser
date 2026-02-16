package com.inventory.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.inventory.app.viewmodel.MainViewModel
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    viewModel: MainViewModel,
    onNavigateToReview: () -> Unit,
    onNavigateToSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val config by viewModel.config.collectAsState()
    val ui by viewModel.uiStrings.collectAsState()

    // Alias dialog state
    var showAliasDialog by remember { mutableStateOf(false) }
    var aliasShort by remember { mutableStateOf("") }
    var aliasMapsTo by remember { mutableStateOf("") }

    // Convert dialog state
    var showConvertDialog by remember { mutableStateOf(false) }
    var convertItem by remember { mutableStateOf("") }
    var convertContainer by remember { mutableStateOf("") }
    var convertFactor by remember { mutableStateOf("") }

    // Snackbar
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Inventory Parser") },
                actions = {
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            // Input field — compact height so results are visible below
            OutlinedTextField(
                value = state.inputText,
                onValueChange = { viewModel.updateInput(it) },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 100.dp, max = 200.dp),
                label = { Text("Paste WhatsApp message") },
                textStyle = LocalTextStyle.current.copy(fontFamily = FontFamily.Monospace),
                maxLines = 10,
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Buttons row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = {
                        viewModel.parse()
                    },
                    modifier = Modifier.weight(1f),
                    enabled = state.inputText.isNotBlank(),
                ) {
                    Text(ui.s("review_parse_btn"))
                }

                OutlinedButton(onClick = { showAliasDialog = true }) {
                    Text(ui.s("cmd_alias"))
                }
                OutlinedButton(onClick = { showConvertDialog = true }) {
                    Text(ui.s("cmd_convert"))
                }
            }

            // Parse results — shown inline below the input
            if (state.isParsed) {
                Spacer(modifier = Modifier.height(12.dp))

                // Notes
                if (state.notes.isNotEmpty()) {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            for (note in state.notes) {
                                Text(
                                    "${ui.s("note_prefix")}: $note",
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Unparseable
                if (state.unparseable.isNotEmpty()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
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
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Rows summary + action buttons
                if (state.rows.isNotEmpty()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer
                        )
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text(
                                "${state.rows.size} rows parsed",
                                style = MaterialTheme.typography.titleMedium,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                            // Show a compact preview of each row
                            for ((idx, row) in state.rows.withIndex()) {
                                val item = row["inv_type"]?.toString() ?: "???"
                                val qty = row["qty"]?.toString() ?: "?"
                                val loc = row["vehicle_sub_unit"]?.toString() ?: ""
                                Text(
                                    "${idx + 1}. $item  $qty  $loc",
                                    style = MaterialTheme.typography.bodySmall,
                                    fontFamily = FontFamily.Monospace,
                                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        // Review & Edit button
                        Button(
                            onClick = onNavigateToReview,
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(ui.s("review_confirm_btn"))
                        }

                        // Discard
                        OutlinedButton(onClick = { viewModel.discard() }) {
                            Text(ui.s("help_quit_desc").take(5))
                        }
                    }
                } else if (state.notes.isEmpty() && state.unparseable.isEmpty()) {
                    Text(
                        ui.s("no_transactions"),
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.align(Alignment.CenterHorizontally)
                    )
                }
            }
        }
    }

    // Alias dialog
    if (showAliasDialog) {
        AlertDialog(
            onDismissRequest = { showAliasDialog = false },
            title = { Text(ui.s("cmd_alias")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = aliasShort,
                        onValueChange = { aliasShort = it },
                        label = { Text(ui.s("alias_short_prompt").trimEnd(' ', ':')) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = aliasMapsTo,
                        onValueChange = { aliasMapsTo = it },
                        label = { Text(ui.s("alias_maps_to_prompt").trimEnd(' ', ':')) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    if (aliasShort.isNotBlank() && aliasMapsTo.isNotBlank()) {
                        viewModel.saveAlias(aliasShort.trim(), aliasMapsTo.trim())
                        scope.launch {
                            snackbarHostState.showSnackbar(
                                ui.s("alias_saved", "alias" to aliasShort.trim(), "item" to aliasMapsTo.trim())
                            )
                        }
                        aliasShort = ""
                        aliasMapsTo = ""
                        showAliasDialog = false
                    }
                }) { Text("Save") }
            },
            dismissButton = {
                TextButton(onClick = {
                    aliasShort = ""
                    aliasMapsTo = ""
                    showAliasDialog = false
                }) { Text("Cancel") }
            },
        )
    }

    // Convert dialog
    if (showConvertDialog) {
        AlertDialog(
            onDismissRequest = { showConvertDialog = false },
            title = { Text(ui.s("cmd_convert")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = convertItem,
                        onValueChange = { convertItem = it },
                        label = { Text(ui.s("convert_item_prompt").trimEnd(' ', ':')) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = convertContainer,
                        onValueChange = { convertContainer = it },
                        label = { Text(ui.s("convert_container_prompt").trimEnd(' ', ':')) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = convertFactor,
                        onValueChange = { convertFactor = it },
                        label = {
                            Text(ui.s("convert_factor_prompt", "container" to convertContainer.ifBlank { "..." }).trimEnd(' ', ':'))
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val factor = convertFactor.toIntOrNull()
                    if (convertItem.isNotBlank() && convertContainer.isNotBlank() && factor != null) {
                        viewModel.saveConversion(convertItem.trim(), convertContainer.trim(), factor)
                        scope.launch {
                            snackbarHostState.showSnackbar(
                                ui.s("conversion_saved",
                                    "container" to convertContainer.trim(),
                                    "item" to convertItem.trim(),
                                    "factor" to factor.toString(),
                                )
                            )
                        }
                        convertItem = ""
                        convertContainer = ""
                        convertFactor = ""
                        showConvertDialog = false
                    }
                }) { Text("Save") }
            },
            dismissButton = {
                TextButton(onClick = {
                    convertItem = ""
                    convertContainer = ""
                    convertFactor = ""
                    showConvertDialog = false
                }) { Text("Cancel") }
            },
        )
    }
}
