package com.inventory.parser

/**
 * Port of Python's difflib.SequenceMatcher using the Ratcliff/Obershelp algorithm.
 *
 * The ratio is: 2.0 * matching_characters / (len(a) + len(b))
 * where matching_characters is found by recursively finding the longest common
 * substring, then matching the left and right remainders.
 */
object SequenceMatcher {

    /**
     * Compute the similarity ratio between two strings using the
     * Ratcliff/Obershelp algorithm (same as Python's difflib.SequenceMatcher).
     */
    fun ratio(a: String, b: String): Double {
        if (a.isEmpty() && b.isEmpty()) return 1.0
        if (a.isEmpty() || b.isEmpty()) return 0.0
        val matches = countMatchingChars(a, 0, a.length, b, 0, b.length)
        return 2.0 * matches / (a.length + b.length)
    }

    /**
     * Recursively count matching characters between a[aStart..aEnd) and b[bStart..bEnd).
     * Finds the longest common substring, then recurses on left and right remainders.
     */
    private fun countMatchingChars(
        a: String, aStart: Int, aEnd: Int,
        b: String, bStart: Int, bEnd: Int
    ): Int {
        // Find the longest common substring
        var bestLen = 0
        var bestA = aStart
        var bestB = bStart

        // Use the standard DP approach for longest common substring
        // lengths[j] = length of longest common suffix ending at b[j-1]
        // We iterate i over a, j over b.
        // We only need a 1D array since we scan in reverse for j.
        val lengths = IntArray(bEnd - bStart + 1)

        for (i in aStart until aEnd) {
            // Scan j in reverse to avoid overwriting values we still need
            val newLengths = IntArray(bEnd - bStart + 1)
            for (j in bStart until bEnd) {
                if (a[i] == b[j]) {
                    val jIdx = j - bStart
                    val prevLen = if (jIdx > 0) lengths[jIdx - 1] else 0
                    newLengths[jIdx] = prevLen + 1
                    if (newLengths[jIdx] > bestLen) {
                        bestLen = newLengths[jIdx]
                        bestA = i - bestLen + 1
                        bestB = j - bestLen + 1
                    }
                }
            }
            for (j in 0 until lengths.size) {
                lengths[j] = newLengths[j]
            }
        }

        if (bestLen == 0) return 0

        // Recurse on the portions before and after the matching block
        var total = bestLen

        // Left remainder: a[aStart..bestA) vs b[bStart..bestB)
        if (bestA > aStart && bestB > bStart) {
            total += countMatchingChars(a, aStart, bestA, b, bStart, bestB)
        }

        // Right remainder: a[bestA+bestLen..aEnd) vs b[bestB+bestLen..bEnd)
        val aRight = bestA + bestLen
        val bRight = bestB + bestLen
        if (aRight < aEnd && bRight < bEnd) {
            total += countMatchingChars(a, aRight, aEnd, b, bRight, bEnd)
        }

        return total
    }

    /**
     * Port of Python's difflib.get_close_matches.
     *
     * Returns the best n matches from [candidates] that have a similarity ratio
     * >= [cutoff] when compared to [word]. Results are sorted by similarity
     * (best first).
     */
    fun getCloseMatches(
        word: String,
        candidates: List<String>,
        n: Int = 3,
        cutoff: Double = 0.6
    ): List<String> {
        val scored = mutableListOf<Pair<Double, String>>()
        for (candidate in candidates) {
            val r = ratio(word, candidate)
            if (r >= cutoff) {
                scored.add(r to candidate)
            }
        }
        // Sort by ratio descending (Python's heapq.nlargest behavior)
        scored.sortByDescending { it.first }
        return scored.take(n).map { it.second }
    }
}

private val SEP_RE = Regex("[\\s_\\-]+")

/**
 * Normalize spaces, dashes, and underscores to single spaces.
 */
fun normalizeSeparators(s: String): String {
    return SEP_RE.replace(s, " ").trim().lowercase()
}

/**
 * Match text against candidates + optional aliases.
 *
 * Returns (canonical_name, match_type) or (null, null).
 * match_type is "exact", "alias", "separator", "prefix", "plural", or "fuzzy".
 */
fun resolve(
    text: String,
    candidates: List<String>,
    aliases: Map<String, String>? = null,
    normalizeSeparators: Boolean = false,
    tryPrefix: Boolean = false,
    tryPlural: Boolean = false,
    cutoff: Double = 0.6
): Pair<String?, String?> {
    val textClean = text.trim()
    if (textClean.isEmpty()) return null to null
    val textLower = textClean.lowercase()

    // 1. Exact match
    for (c in candidates) {
        if (c.lowercase() == textLower) {
            return c to "exact"
        }
    }

    // 2. Exact alias
    if (aliases != null) {
        for ((a, target) in aliases) {
            if (a.lowercase() == textLower) {
                return target to "alias"
            }
        }
    }

    // 3. Separator-normalized (space/dash/underscore equivalence)
    if (normalizeSeparators) {
        val textNorm = com.inventory.parser.normalizeSeparators(textClean)
        for (c in candidates) {
            if (com.inventory.parser.normalizeSeparators(c) == textNorm) {
                return c to "separator"
            }
        }
        if (aliases != null) {
            for ((a, target) in aliases) {
                if (com.inventory.parser.normalizeSeparators(a) == textNorm) {
                    return target to "separator"
                }
            }
        }
    }

    // 4. Plural normalization
    if (tryPlural) {
        val textStripped = textLower.trimEnd('s')
        for (c in candidates.sortedByDescending { it.length }) {
            val cl = c.lowercase()
            if (textStripped == cl || textStripped == cl.trimEnd('s')) {
                return c to "plural"
            }
        }
    }

    // 5. Prefix match
    if (tryPrefix) {
        for (c in candidates.sortedByDescending { it.length }) {
            if (c.lowercase().startsWith(textLower)) {
                return c to "prefix"
            }
        }
    }

    // 6. Fuzzy match
    val allTargets = candidates.map { it.lowercase() }.toMutableList()
    if (aliases != null) {
        allTargets.addAll(aliases.keys.map { it.lowercase() })
    }
    val shortCutoff = if (textLower.length <= 4) maxOf(cutoff, 0.8) else cutoff
    val matches = SequenceMatcher.getCloseMatches(textLower, allTargets, n = 1, cutoff = shortCutoff)
    if (matches.isNotEmpty()) {
        val match = matches[0]
        if (aliases != null) {
            for ((a, target) in aliases) {
                if (a.lowercase() == match) {
                    return target to "fuzzy"
                }
            }
        }
        for (c in candidates) {
            if (c.lowercase() == match) {
                return c to "fuzzy"
            }
        }
    }

    return null to null
}

/**
 * Escape a string for use in a regex pattern, character by character.
 * Matches Python's re.escape() behavior (Python 3.7+): characters in the set
 * ()[]{}?*+-|^$\.&~# \t\n\r\v\f are escaped with a backslash.
 * Non-ASCII characters and underscores are NOT escaped (matching Python behavior).
 */
private val PYTHON_SPECIAL_CHARS = setOf(
    '(', ')', '[', ']', '{', '}', '?', '*', '+', '-', '|', '^', '$',
    '\\', '.', '&', '~', '#', ' ', '\t', '\n', '\r',
    '\u000B', // \v vertical tab
    '\u000C', // \f form feed
)

private fun reEscape(text: String): String {
    val sb = StringBuilder()
    for (ch in text) {
        if (ch in PYTHON_SPECIAL_CHARS) {
            sb.append('\\')
        }
        sb.append(ch)
    }
    return sb.toString()
}

/**
 * Build a word-boundary regex pattern with separator normalization.
 */
fun boundaryPattern(text: String): String {
    val escaped = reEscape(text)
    // After reEscape: space -> "\ ", dash -> "\-", underscore -> "_" (not escaped, matching Python)
    // Replace sequences of (escaped-space | escaped-dash | underscore) with separator class
    val pattern = Regex("""(\\ |\\-|_)+""").replace(escaped) { "[\\s_-]+" }
    return if (text.length <= 2 && !text.isAscii()) {
        "(?:^|(?<=\\s))${pattern}(?=\\s|$)"
    } else {
        "(?:^|(?<=\\s)|(?<=\\b))${pattern}(?=\\s|$|\\b)"
    }
}

/**
 * Resolve text against candidates + optional aliases (no prefix/plural/separator).
 *
 * Returns (canonical_name, match_type) where match_type is
 * "exact", "alias", "fuzzy", or (null, null) if no match.
 */
fun fuzzyResolve(
    text: String,
    candidates: List<String>,
    aliases: Map<String, String>? = null,
    cutoff: Double = 0.6
): Pair<String?, String?> {
    return resolve(text, candidates, aliases, cutoff = cutoff)
}

/**
 * Check if a string contains only ASCII characters.
 * Equivalent to Python's str.isascii().
 */
fun String.isAscii(): Boolean = all { it.code < 128 }
