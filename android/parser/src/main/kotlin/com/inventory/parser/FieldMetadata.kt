package com.inventory.parser

/**
 * Field ordering, closed-set metadata, and required-field helpers.
 * Ports get_field_order(), get_closed_set_fields(), get_required_fields(),
 * get_closed_set_options() from inventory_core.py.
 */

val DEFAULT_FIELD_ORDER = listOf("date", "inv_type", "qty", "trans_type", "vehicle_sub_unit", "batch", "notes")

val DEFAULT_FIELD_OPTIONS = mapOf(
    "inv_type" to "items",
    "trans_type" to "transaction_types",
    "vehicle_sub_unit" to "locations",
)

fun getFieldOrder(config: Map<String, Any?>): List<String> {
    @Suppress("UNCHECKED_CAST")
    val ui = config["ui"] as? Map<String, Any?> ?: return DEFAULT_FIELD_ORDER
    @Suppress("UNCHECKED_CAST")
    return ui["field_order"] as? List<String> ?: DEFAULT_FIELD_ORDER
}

fun getClosedSetFields(config: Map<String, Any?>): Set<String> {
    @Suppress("UNCHECKED_CAST")
    val fo = config["field_options"] as? Map<String, String> ?: DEFAULT_FIELD_OPTIONS
    return fo.keys
}

fun getRequiredFields(config: Map<String, Any?>): List<String> {
    @Suppress("UNCHECKED_CAST")
    return config["required_fields"] as? List<String> ?: listOf("trans_type", "vehicle_sub_unit")
}

fun getClosedSetOptions(field: String, config: Map<String, Any?>): List<String> {
    @Suppress("UNCHECKED_CAST")
    val fieldOptions = config["field_options"] as? Map<String, String> ?: DEFAULT_FIELD_OPTIONS
    val configKey = fieldOptions[field]

    if (configKey != null) {
        @Suppress("UNCHECKED_CAST")
        val options = (config[configKey] as? List<String>)?.toMutableList() ?: mutableListOf()
        if (field == "vehicle_sub_unit") {
            val src = config["default_source"] as? String ?: "warehouse"
            if (src !in options) options.add(0, src)
        }
        return options
    }

    // Legacy fallback
    @Suppress("UNCHECKED_CAST")
    return when (field) {
        "inv_type" -> config["items"] as? List<String> ?: emptyList()
        "trans_type" -> config["transaction_types"] as? List<String> ?: emptyList()
        "vehicle_sub_unit" -> {
            val locs = (config["locations"] as? List<String>)?.toMutableList() ?: mutableListOf()
            val src = config["default_source"] as? String ?: "warehouse"
            if (src !in locs) locs.add(0, src)
            locs
        }
        else -> emptyList()
    }
}
