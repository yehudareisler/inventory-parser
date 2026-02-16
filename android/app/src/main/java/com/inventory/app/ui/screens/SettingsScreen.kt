package com.inventory.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.inventory.app.viewmodel.MainViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: MainViewModel,
    onBack: () -> Unit,
) {
    val config by viewModel.config.collectAsState()
    val authState by viewModel.authManager.authState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Google Sheets connection
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Google Sheets", style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(8.dp))

                        if (authState.isSignedIn) {
                            Text("Signed in as: ${authState.email ?: "Unknown"}")
                            Spacer(modifier = Modifier.height(4.dp))
                            OutlinedButton(onClick = { viewModel.authManager.signOut() }) {
                                Text("Sign out")
                            }
                        } else {
                            Text("Not signed in")
                            if (authState.error != null) {
                                Text(
                                    "Error: ${authState.error}",
                                    color = MaterialTheme.colorScheme.error,
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        @Suppress("UNCHECKED_CAST")
                        val gs = config["google_sheets"] as? Map<String, Any?> ?: emptyMap()
                        val spreadsheetId = gs["spreadsheet_id"] as? String ?: ""
                        var sheetId by remember(spreadsheetId) { mutableStateOf(spreadsheetId) }

                        OutlinedTextField(
                            value = sheetId,
                            onValueChange = {
                                sheetId = it
                                @Suppress("UNCHECKED_CAST")
                                val current = (config["google_sheets"] as? Map<String, Any?>)?.toMutableMap() ?: mutableMapOf()
                                current["spreadsheet_id"] = it
                                viewModel.updateConfigField("google_sheets", current)
                            },
                            label = { Text("Spreadsheet ID") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                        )
                    }
                }
            }

            // Default source
            item {
                val defaultSource = config["default_source"] as? String ?: "warehouse"
                var value by remember(defaultSource) { mutableStateOf(defaultSource) }
                OutlinedTextField(
                    value = value,
                    onValueChange = {
                        value = it
                        viewModel.updateConfigField("default_source", it)
                    },
                    label = { Text("Default source") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
            }

            // Items list
            item {
                @Suppress("UNCHECKED_CAST")
                val items = config["items"] as? List<String> ?: emptyList()
                ListSection(
                    title = "Items",
                    items = items,
                    onAdd = { newItem ->
                        viewModel.updateConfigField("items", items + newItem)
                    },
                    onRemove = { idx ->
                        viewModel.updateConfigField("items", items.toMutableList().apply { removeAt(idx) })
                    }
                )
            }

            // Locations list
            item {
                @Suppress("UNCHECKED_CAST")
                val locations = config["locations"] as? List<String> ?: emptyList()
                ListSection(
                    title = "Locations",
                    items = locations,
                    onAdd = { newLoc ->
                        viewModel.updateConfigField("locations", locations + newLoc)
                    },
                    onRemove = { idx ->
                        viewModel.updateConfigField("locations", locations.toMutableList().apply { removeAt(idx) })
                    }
                )
            }

            // Transaction types
            item {
                @Suppress("UNCHECKED_CAST")
                val types = config["transaction_types"] as? List<String> ?: emptyList()
                ListSection(
                    title = "Transaction types",
                    items = types,
                    onAdd = { newType ->
                        viewModel.updateConfigField("transaction_types", types + newType)
                    },
                    onRemove = { idx ->
                        viewModel.updateConfigField("transaction_types", types.toMutableList().apply { removeAt(idx) })
                    }
                )
            }

            // Aliases
            item {
                @Suppress("UNCHECKED_CAST")
                val aliases = config["aliases"] as? Map<String, String> ?: emptyMap()
                KeyValueSection(
                    title = "Aliases",
                    entries = aliases,
                    keyLabel = "Short name",
                    valueLabel = "Maps to",
                    onAdd = { key, value ->
                        val updated = aliases.toMutableMap()
                        updated[key] = value
                        viewModel.updateConfigField("aliases", updated)
                    },
                    onRemove = { key ->
                        val updated = aliases.toMutableMap()
                        updated.remove(key)
                        viewModel.updateConfigField("aliases", updated)
                    }
                )
            }

            // Default transfer type
            item {
                val defaultType = config["default_transfer_type"] as? String ?: "warehouse_to_branch"
                var value by remember(defaultType) { mutableStateOf(defaultType) }
                OutlinedTextField(
                    value = value,
                    onValueChange = {
                        value = it
                        viewModel.updateConfigField("default_transfer_type", it)
                    },
                    label = { Text("Default transfer type") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
            }
        }
    }
}

@Composable
private fun ListSection(
    title: String,
    items: List<String>,
    onAdd: (String) -> Unit,
    onRemove: (Int) -> Unit,
) {
    var newItem by remember { mutableStateOf("") }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))

            for ((idx, item) in items.withIndex()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(item, modifier = Modifier.weight(1f))
                    IconButton(onClick = { onRemove(idx) }) {
                        Icon(
                            Icons.Default.Delete,
                            contentDescription = "Remove",
                            tint = MaterialTheme.colorScheme.error,
                        )
                    }
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    value = newItem,
                    onValueChange = { newItem = it },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    label = { Text("Add $title") },
                )
                IconButton(
                    onClick = {
                        if (newItem.isNotBlank()) {
                            onAdd(newItem.trim())
                            newItem = ""
                        }
                    }
                ) {
                    Icon(Icons.Default.Add, contentDescription = "Add")
                }
            }
        }
    }
}

@Composable
private fun KeyValueSection(
    title: String,
    entries: Map<String, String>,
    keyLabel: String,
    valueLabel: String,
    onAdd: (String, String) -> Unit,
    onRemove: (String) -> Unit,
) {
    var newKey by remember { mutableStateOf("") }
    var newValue by remember { mutableStateOf("") }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))

            for ((key, value) in entries) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "$key \u2192 $value",
                        modifier = Modifier.weight(1f),
                    )
                    IconButton(onClick = { onRemove(key) }) {
                        Icon(
                            Icons.Default.Delete,
                            contentDescription = "Remove",
                            tint = MaterialTheme.colorScheme.error,
                        )
                    }
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = newKey,
                    onValueChange = { newKey = it },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    label = { Text(keyLabel) },
                )
                OutlinedTextField(
                    value = newValue,
                    onValueChange = { newValue = it },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    label = { Text(valueLabel) },
                )
                IconButton(
                    onClick = {
                        if (newKey.isNotBlank() && newValue.isNotBlank()) {
                            onAdd(newKey.trim(), newValue.trim())
                            newKey = ""
                            newValue = ""
                        }
                    }
                ) {
                    Icon(Icons.Default.Add, contentDescription = "Add")
                }
            }
        }
    }
}
