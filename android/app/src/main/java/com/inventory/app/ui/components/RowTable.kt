package com.inventory.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.inventory.parser.*

private val COL_WIDTHS = mapOf(
    "#" to 40.dp,
    "DATE" to 100.dp,
    "ITEM" to 150.dp,
    "QTY" to 100.dp,
    "TYPE" to 140.dp,
    "LOCATION" to 100.dp,
    "BATCH" to 60.dp,
    "NOTES" to 150.dp,
)

@Composable
fun RowTable(
    rows: List<Map<String, Any?>>,
    config: Map<String, Any?>,
    onCellClick: (rowIdx: Int, field: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val fieldOrder = getFieldOrder(config)
    val uiStrings = UiStrings(config)
    val headers = uiStrings.tableHeaders

    Column(modifier = modifier.horizontalScroll(rememberScrollState())) {
        // Header row
        Row(modifier = Modifier.background(MaterialTheme.colorScheme.surfaceVariant)) {
            for (header in headers) {
                val width = COL_WIDTHS[header] ?: 100.dp
                TableCell(
                    text = header,
                    width = width,
                    fontWeight = FontWeight.Bold,
                )
            }
        }

        HorizontalDivider()

        // Data rows
        for ((i, row) in rows.withIndex()) {
            val hasWarning = rowHasWarning(row, config)
            val bgColor = if (hasWarning) {
                MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
            } else if (i % 2 == 0) {
                MaterialTheme.colorScheme.surface
            } else {
                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)
            }

            Row(modifier = Modifier.background(bgColor)) {
                // Row number
                val warn = if (hasWarning) "\u26a0 " else ""
                TableCell(
                    text = "$warn${i + 1}",
                    width = COL_WIDTHS["#"] ?: 40.dp,
                )

                // Data cells
                for ((fi, field) in fieldOrder.withIndex()) {
                    val headerName = if (fi + 1 < headers.size) headers[fi + 1] else field.uppercase()
                    val width = COL_WIDTHS[headerName] ?: 100.dp
                    TableCell(
                        text = formatCell(row, field),
                        width = width,
                        onClick = { onCellClick(i, field) },
                    )
                }
            }

            HorizontalDivider(thickness = 0.5.dp)
        }
    }
}

@Composable
private fun TableCell(
    text: String,
    width: Dp,
    fontWeight: FontWeight = FontWeight.Normal,
    onClick: (() -> Unit)? = null,
) {
    val mod = Modifier
        .width(width)
        .padding(horizontal = 6.dp, vertical = 8.dp)
        .let { if (onClick != null) it.clickable(onClick = onClick) else it }

    Text(
        text = text,
        modifier = mod,
        fontSize = 13.sp,
        fontFamily = FontFamily.Monospace,
        fontWeight = fontWeight,
        maxLines = 2,
        overflow = TextOverflow.Ellipsis,
    )
}
