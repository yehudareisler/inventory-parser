package com.inventory.app.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.inventory.app.BuildConfig
import com.inventory.app.update.UpdateResult
import com.inventory.app.viewmodel.MainViewModel
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: MainViewModel,
    onBack: () -> Unit,
) {
    val config by viewModel.config.collectAsState()
    val authState by viewModel.authManager.authState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    val yamlPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            viewModel.loadYamlConfig(uri) { error ->
                scope.launch {
                    if (error == null) {
                        snackbarHostState.showSnackbar("Config loaded successfully!")
                    } else {
                        snackbarHostState.showSnackbar(error)
                    }
                }
            }
        }
    }

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
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Load YAML config
            item {
                Button(
                    onClick = { yamlPicker.launch(arrayOf("*/*")) },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Load YAML config file")
                }
            }

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

            // GitHub token (for private repo updates)
            item {
                val ghToken = config["github_token"] as? String ?: ""
                var tokenValue by remember(ghToken) { mutableStateOf(ghToken) }
                OutlinedTextField(
                    value = tokenValue,
                    onValueChange = {
                        tokenValue = it
                        viewModel.updateConfigField("github_token", it)
                    },
                    label = { Text("GitHub token (for updates)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
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

            // Action verbs
            item {
                @Suppress("UNCHECKED_CAST")
                val actionVerbs = config["action_verbs"] as? Map<String, Any?> ?: emptyMap()
                ActionVerbsSection(
                    verbs = actionVerbs,
                    onUpdate = { updated -> viewModel.updateConfigField("action_verbs", updated) }
                )
            }

            // Unit conversions
            item {
                @Suppress("UNCHECKED_CAST")
                val conversions = config["unit_conversions"] as? Map<String, Any?> ?: emptyMap()
                UnitConversionsSection(
                    conversions = conversions,
                    onUpdate = { updated -> viewModel.updateConfigField("unit_conversions", updated) }
                )
            }

            // Non-zero-sum types
            item {
                @Suppress("UNCHECKED_CAST")
                val nzsTypes = config["non_zero_sum_types"] as? List<String> ?: emptyList()
                ListSection(
                    title = "Non-zero-sum types",
                    items = nzsTypes,
                    onAdd = { newType ->
                        viewModel.updateConfigField("non_zero_sum_types", nzsTypes + newType)
                    },
                    onRemove = { idx ->
                        viewModel.updateConfigField("non_zero_sum_types", nzsTypes.toMutableList().apply { removeAt(idx) })
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

            // Check for updates
            item {
                var checking by remember { mutableStateOf(false) }
                var updateResult by remember { mutableStateOf<UpdateResult?>(null) }
                var showUpdateDialog by remember { mutableStateOf(false) }

                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("About", style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            "Version: ${BuildConfig.VERSION_NAME}",
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Spacer(modifier = Modifier.height(8.dp))

                        Button(
                            onClick = {
                                checking = true
                                viewModel.checkForUpdate { result ->
                                    checking = false
                                    updateResult = result
                                    if (result.available) {
                                        showUpdateDialog = true
                                    } else {
                                        scope.launch {
                                            snackbarHostState.showSnackbar(
                                                "Up to date (${result.latestTag})"
                                            )
                                        }
                                    }
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !checking,
                        ) {
                            if (checking) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(18.dp),
                                    strokeWidth = 2.dp,
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                            }
                            Text(if (checking) "Checking..." else "Check for updates")
                        }
                    }
                }

                if (showUpdateDialog && updateResult?.available == true) {
                    AlertDialog(
                        onDismissRequest = { showUpdateDialog = false },
                        title = { Text("Update available") },
                        text = {
                            Text("New version: ${updateResult!!.releaseName ?: updateResult!!.latestTag}\n\nCurrent: ${BuildConfig.VERSION_NAME}")
                        },
                        confirmButton = {
                            TextButton(onClick = {
                                val assetId = updateResult!!.apkAssetId
                                if (assetId != null) {
                                    viewModel.downloadUpdate(assetId) { success, message ->
                                        scope.launch {
                                            snackbarHostState.showSnackbar(message)
                                        }
                                    }
                                } else {
                                    scope.launch {
                                        snackbarHostState.showSnackbar("No APK asset found in release")
                                    }
                                }
                                showUpdateDialog = false
                            }) { Text("Download") }
                        },
                        dismissButton = {
                            TextButton(onClick = { showUpdateDialog = false }) { Text("Later") }
                        },
                    )
                }
            }
        }
    }
}

// ============================================================
// Action Verbs Section (nested: trans_type → verb list)
// ============================================================

@Composable
private fun ActionVerbsSection(
    verbs: Map<String, Any?>,
    onUpdate: (Map<String, Any?>) -> Unit,
) {
    var showAddDialog by remember { mutableStateOf(false) }
    var addTransType by remember { mutableStateOf("") }
    var addVerb by remember { mutableStateOf("") }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Action verbs", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))

            for ((transType, verbsAny) in verbs) {
                @Suppress("UNCHECKED_CAST")
                val verbList = (verbsAny as? List<*>)?.filterIsInstance<String>() ?: continue
                Text(
                    transType,
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                for (verb in verbList) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(start = 16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(verb, modifier = Modifier.weight(1f))
                        IconButton(onClick = {
                            val updated = verbs.toMutableMap()
                            @Suppress("UNCHECKED_CAST")
                            val updatedList = (updated[transType] as? List<*>)
                                ?.filterIsInstance<String>()?.toMutableList() ?: return@IconButton
                            updatedList.remove(verb)
                            if (updatedList.isEmpty()) {
                                updated.remove(transType)
                            } else {
                                updated[transType] = updatedList
                            }
                            onUpdate(updated)
                        }) {
                            Icon(
                                Icons.Default.Delete,
                                contentDescription = "Remove",
                                tint = MaterialTheme.colorScheme.error,
                                modifier = Modifier.size(18.dp),
                            )
                        }
                    }
                }
            }

            // Add button
            OutlinedButton(
                onClick = { showAddDialog = true },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Add verb")
            }
        }
    }

    if (showAddDialog) {
        AlertDialog(
            onDismissRequest = { showAddDialog = false },
            title = { Text("Add action verb") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = addTransType,
                        onValueChange = { addTransType = it },
                        label = { Text("Transaction type") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = addVerb,
                        onValueChange = { addVerb = it },
                        label = { Text("Verb") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    if (addTransType.isNotBlank() && addVerb.isNotBlank()) {
                        val updated = verbs.toMutableMap()
                        @Suppress("UNCHECKED_CAST")
                        val existing = (updated[addTransType.trim()] as? List<*>)
                            ?.filterIsInstance<String>()?.toMutableList() ?: mutableListOf()
                        existing.add(addVerb.trim())
                        updated[addTransType.trim()] = existing
                        onUpdate(updated)
                        addTransType = ""
                        addVerb = ""
                        showAddDialog = false
                    }
                }) { Text("Add") }
            },
            dismissButton = {
                TextButton(onClick = {
                    addTransType = ""
                    addVerb = ""
                    showAddDialog = false
                }) { Text("Cancel") }
            },
        )
    }
}

// ============================================================
// Unit Conversions Section (nested: item → container → factor)
// ============================================================

@Composable
private fun UnitConversionsSection(
    conversions: Map<String, Any?>,
    onUpdate: (Map<String, Any?>) -> Unit,
) {
    var showAddDialog by remember { mutableStateOf(false) }
    var addItem by remember { mutableStateOf("") }
    var addContainer by remember { mutableStateOf("") }
    var addFactor by remember { mutableStateOf("") }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Unit conversions", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))

            for ((item, convsAny) in conversions) {
                @Suppress("UNCHECKED_CAST")
                val convMap = convsAny as? Map<String, Any?> ?: continue
                Text(
                    item,
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                for ((container, factorAny) in convMap) {
                    if (container == "base_unit") continue
                    val factor = (factorAny as? Number)?.toInt() ?: continue
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(start = 16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            "1 $container = $factor",
                            modifier = Modifier.weight(1f),
                        )
                        IconButton(onClick = {
                            val updated = conversions.toMutableMap()
                            @Suppress("UNCHECKED_CAST")
                            val itemConvs = (updated[item] as? Map<String, Any?>)?.toMutableMap() ?: return@IconButton
                            itemConvs.remove(container)
                            if (itemConvs.keys.all { it == "base_unit" }) {
                                updated.remove(item)
                            } else {
                                updated[item] = itemConvs
                            }
                            onUpdate(updated)
                        }) {
                            Icon(
                                Icons.Default.Delete,
                                contentDescription = "Remove",
                                tint = MaterialTheme.colorScheme.error,
                                modifier = Modifier.size(18.dp),
                            )
                        }
                    }
                }
            }

            // Add button
            OutlinedButton(
                onClick = { showAddDialog = true },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Add conversion")
            }
        }
    }

    if (showAddDialog) {
        AlertDialog(
            onDismissRequest = { showAddDialog = false },
            title = { Text("Add unit conversion") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = addItem,
                        onValueChange = { addItem = it },
                        label = { Text("Item name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = addContainer,
                        onValueChange = { addContainer = it },
                        label = { Text("Container name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = addFactor,
                        onValueChange = { addFactor = it },
                        label = { Text("Units per container") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val factor = addFactor.toIntOrNull()
                    if (addItem.isNotBlank() && addContainer.isNotBlank() && factor != null) {
                        val updated = conversions.toMutableMap()
                        @Suppress("UNCHECKED_CAST")
                        val itemConvs = (updated[addItem.trim()] as? Map<String, Any?>)?.toMutableMap()
                            ?: mutableMapOf<String, Any?>()
                        itemConvs[addContainer.trim()] = factor
                        updated[addItem.trim()] = itemConvs
                        onUpdate(updated)
                        addItem = ""
                        addContainer = ""
                        addFactor = ""
                        showAddDialog = false
                    }
                }) { Text("Add") }
            },
            dismissButton = {
                TextButton(onClick = {
                    addItem = ""
                    addContainer = ""
                    addFactor = ""
                    showAddDialog = false
                }) { Text("Cancel") }
            },
        )
    }
}

// ============================================================
// Reusable list/key-value sections
// ============================================================

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
