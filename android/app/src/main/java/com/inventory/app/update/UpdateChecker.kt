package com.inventory.app.update

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Environment
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import javax.inject.Inject
import javax.inject.Singleton

data class ReleaseInfo(
    @SerializedName("tag_name") val tagName: String,
    val name: String?,
    val assets: List<ReleaseAsset>?,
)

data class ReleaseAsset(
    val name: String,
    @SerializedName("browser_download_url") val downloadUrl: String,
    val size: Long,
    val id: Long,
)

data class UpdateResult(
    val available: Boolean,
    val currentTag: String,
    val latestTag: String,
    val apkUrl: String? = null,
    val apkAssetId: Long? = null,
    val releaseName: String? = null,
)

/**
 * Checks GitHub Releases for newer builds and triggers APK download.
 * Supports private repos via a GitHub personal access token.
 */
@Singleton
class UpdateChecker @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    // Client that does NOT follow redirects — we need the signed redirect URL
    private val noRedirectClient = OkHttpClient.Builder()
        .followRedirects(false)
        .build()
    private val client = OkHttpClient()
    private val gson = Gson()

    /**
     * Check if a newer release exists on GitHub.
     * For private repos, pass a GitHub PAT as [token].
     */
    suspend fun checkForUpdate(
        owner: String,
        repo: String,
        currentVersionName: String,
        token: String? = null,
    ): UpdateResult = withContext(Dispatchers.IO) {
        val url = "https://api.github.com/repos/$owner/$repo/releases/latest"
        val reqBuilder = Request.Builder()
            .url(url)
            .header("Accept", "application/vnd.github+json")
        if (!token.isNullOrBlank()) {
            reqBuilder.header("Authorization", "Bearer $token")
        }

        val response = client.newCall(reqBuilder.build()).execute()
        if (!response.isSuccessful) {
            return@withContext UpdateResult(
                available = false,
                currentTag = currentVersionName,
                latestTag = if (response.code == 404) "no releases (or bad token)" else "HTTP ${response.code}",
            )
        }

        val body = response.body?.string() ?: return@withContext UpdateResult(
            available = false,
            currentTag = currentVersionName,
            latestTag = "empty response",
        )

        val release = gson.fromJson(body, ReleaseInfo::class.java)
        val apkAsset = release.assets?.firstOrNull { it.name.endsWith(".apk") }
        val isNewer = release.tagName != "build-$currentVersionName"
            && release.tagName != currentVersionName

        UpdateResult(
            available = isNewer && apkAsset != null,
            currentTag = currentVersionName,
            latestTag = release.tagName,
            apkUrl = apkAsset?.downloadUrl,
            apkAssetId = apkAsset?.id,
            releaseName = release.name,
        )
    }

    /**
     * Download APK from a private repo release asset.
     * Uses the GitHub API to get a signed redirect URL, then hands it to DownloadManager.
     */
    suspend fun downloadApk(
        owner: String,
        repo: String,
        assetId: Long,
        token: String,
        fileName: String = "inventory-parser-update.apk",
    ): Long = withContext(Dispatchers.IO) {
        // Request the asset with octet-stream accept → GitHub returns 302 to a signed S3 URL
        val apiUrl = "https://api.github.com/repos/$owner/$repo/releases/assets/$assetId"
        val request = Request.Builder()
            .url(apiUrl)
            .header("Accept", "application/octet-stream")
            .header("Authorization", "Bearer $token")
            .build()

        val response = noRedirectClient.newCall(request).execute()
        val signedUrl = if (response.isRedirect) {
            response.header("Location") ?: throw Exception("No redirect URL")
        } else {
            throw Exception("Expected redirect, got ${response.code}")
        }

        // DownloadManager can handle the signed URL without auth
        val dm = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val dmRequest = DownloadManager.Request(Uri.parse(signedUrl))
            .setTitle("Inventory Parser Update")
            .setDescription("Downloading new version...")
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setMimeType("application/vnd.android.package-archive")

        dm.enqueue(dmRequest)
    }
}
