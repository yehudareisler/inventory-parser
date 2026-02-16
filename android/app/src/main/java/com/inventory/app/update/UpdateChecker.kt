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
)

data class UpdateResult(
    val available: Boolean,
    val currentTag: String,
    val latestTag: String,
    val apkUrl: String? = null,
    val releaseName: String? = null,
)

/**
 * Checks GitHub Releases for newer builds and triggers APK download.
 */
@Singleton
class UpdateChecker @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val client = OkHttpClient()
    private val gson = Gson()

    /**
     * Check if a newer release exists on GitHub.
     * Compares the latest release tag against the app's BuildConfig.VERSION_NAME.
     */
    suspend fun checkForUpdate(
        owner: String,
        repo: String,
        currentVersionName: String,
    ): UpdateResult = withContext(Dispatchers.IO) {
        val url = "https://api.github.com/repos/$owner/$repo/releases/latest"
        val request = Request.Builder()
            .url(url)
            .header("Accept", "application/vnd.github+json")
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            return@withContext UpdateResult(
                available = false,
                currentTag = currentVersionName,
                latestTag = "unknown",
            )
        }

        val body = response.body?.string() ?: return@withContext UpdateResult(
            available = false,
            currentTag = currentVersionName,
            latestTag = "unknown",
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
            releaseName = release.name,
        )
    }

    /**
     * Start downloading the APK via Android DownloadManager.
     * Returns the download ID for tracking.
     */
    fun downloadApk(apkUrl: String, fileName: String = "inventory-parser-update.apk"): Long {
        val dm = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val request = DownloadManager.Request(Uri.parse(apkUrl))
            .setTitle("Inventory Parser Update")
            .setDescription("Downloading new version...")
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setMimeType("application/vnd.android.package-archive")

        return dm.enqueue(request)
    }
}
