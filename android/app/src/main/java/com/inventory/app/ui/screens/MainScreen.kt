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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    viewModel: MainViewModel,
    onNavigateToReview: () -> Unit,
    onNavigateToSettings: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val ui by viewModel.uiStrings.collectAsState()

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
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            // Input field
            OutlinedTextField(
                value = state.inputText,
                onValueChange = { viewModel.updateInput(it) },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 200.dp),
                label = { Text("Paste WhatsApp message") },
                textStyle = LocalTextStyle.current.copy(fontFamily = FontFamily.Monospace),
                maxLines = Int.MAX_VALUE,
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Parse button
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = {
                        viewModel.parse()
                        if (viewModel.state.value.rows.isNotEmpty()) {
                            onNavigateToReview()
                        }
                    },
                    modifier = Modifier.weight(1f),
                    enabled = state.inputText.isNotBlank(),
                ) {
                    Text(ui.s("review_parse_btn"))
                }

                // Quick action buttons
                OutlinedButton(onClick = { /* TODO: alias dialog */ }) {
                    Text(ui.s("cmd_alias"))
                }
                OutlinedButton(onClick = { /* TODO: convert dialog */ }) {
                    Text(ui.s("cmd_convert"))
                }
            }

            // Show parse summary if parsed with no rows
            if (state.isParsed && state.rows.isEmpty()) {
                Spacer(modifier = Modifier.height(16.dp))

                if (state.notes.isNotEmpty()) {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(
                                ui.s("note_prefix"),
                                style = MaterialTheme.typography.titleSmall
                            )
                            for (note in state.notes) {
                                Text(note, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    }
                }

                if (state.unparseable.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(
                                ui.s("unparseable_prefix"),
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.onErrorContainer
                            )
                            for (line in state.unparseable) {
                                Text(
                                    line,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onErrorContainer
                                )
                            }
                        }
                    }
                }

                if (state.notes.isEmpty() && state.unparseable.isEmpty()) {
                    Text(
                        ui.s("no_transactions"),
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.align(Alignment.CenterHorizontally)
                    )
                }
            }
        }
    }
}
