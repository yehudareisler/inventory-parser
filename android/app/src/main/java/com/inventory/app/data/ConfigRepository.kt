package com.inventory.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "inventory_config")

@Singleton
class ConfigRepository @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val gson = Gson()
    private val configKey = stringPreferencesKey("parser_config")

    private val defaultConfig: Map<String, Any?> = mapOf(
        "items" to listOf<String>(),
        "aliases" to mapOf<String, String>(),
        "locations" to listOf<String>(),
        "default_source" to "warehouse",
        "transaction_types" to listOf<String>(),
        "action_verbs" to mapOf<String, List<String>>(),
        "unit_conversions" to mapOf<String, Map<String, Number>>(),
        "prepositions" to mapOf(
            "to" to listOf("to", "into"),
            "by" to listOf("by"),
            "from" to listOf("from"),
        ),
        "from_words" to listOf("from"),
        "filler_words" to listOf("\\bthat's\\b", "\\bwhat\\b", "\\bthe\\b", "\\bof\\b", "\\ba\\b", "\\ban\\b", "\\bsome\\b", "\\bvia\\b"),
        "non_zero_sum_types" to listOf("eaten", "starting_point", "recount", "supplier_to_warehouse"),
        "default_transfer_type" to "warehouse_to_branch",
    )

    val configFlow: Flow<Map<String, Any?>> = context.dataStore.data.map { prefs ->
        val json = prefs[configKey]
        if (json != null) {
            try {
                val type = object : TypeToken<Map<String, Any?>>() {}.type
                gson.fromJson<Map<String, Any?>>(json, type) ?: defaultConfig
            } catch (_: Exception) {
                defaultConfig
            }
        } else {
            defaultConfig
        }
    }

    suspend fun saveConfig(config: Map<String, Any?>) {
        context.dataStore.edit { prefs ->
            prefs[configKey] = gson.toJson(config)
        }
    }

    suspend fun updateConfig(transform: (MutableMap<String, Any?>) -> Unit) {
        context.dataStore.edit { prefs ->
            val current = prefs[configKey]?.let { json ->
                try {
                    val type = object : TypeToken<Map<String, Any?>>() {}.type
                    gson.fromJson<Map<String, Any?>>(json, type)?.toMutableMap()
                } catch (_: Exception) { null }
            } ?: defaultConfig.toMutableMap()
            transform(current)
            prefs[configKey] = gson.toJson(current)
        }
    }

    suspend fun addAlias(alias: String, target: String) {
        updateConfig { config ->
            @Suppress("UNCHECKED_CAST")
            val aliases = (config["aliases"] as? Map<String, String>)?.toMutableMap() ?: mutableMapOf()
            aliases[alias] = target
            config["aliases"] = aliases
        }
    }

    suspend fun addConversion(item: String, container: String, factor: Number) {
        updateConfig { config ->
            @Suppress("UNCHECKED_CAST")
            val convs = (config["unit_conversions"] as? Map<String, Map<String, Number>>)?.toMutableMap() ?: mutableMapOf()
            val itemConvs = convs[item]?.toMutableMap() ?: mutableMapOf()
            itemConvs[container] = factor
            convs[item] = itemConvs
            config["unit_conversions"] = convs
        }
    }
}
