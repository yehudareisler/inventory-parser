package com.inventory.app.sheets

import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

data class AuthState(
    val isSignedIn: Boolean = false,
    val accessToken: String? = null,
    val email: String? = null,
    val error: String? = null,
)

/**
 * Manages Google Sign-In for Sheets API access.
 *
 * Uses Android Credential Manager for modern sign-in flow.
 * The actual OAuth token exchange for Sheets scope happens
 * via Google Identity Services authorization request.
 */
@Singleton
class AuthManager @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val _authState = MutableStateFlow(AuthState())
    val authState: StateFlow<AuthState> = _authState.asStateFlow()

    /**
     * Sign in using Credential Manager.
     * Must be called from an Activity context for the UI flow.
     */
    suspend fun signIn(activityContext: Context, webClientId: String) {
        try {
            val credentialManager = CredentialManager.create(activityContext)

            val googleIdOption = GetGoogleIdOption.Builder()
                .setServerClientId(webClientId)
                .setFilterByAuthorizedAccounts(false)
                .build()

            val request = GetCredentialRequest.Builder()
                .addCredentialOption(googleIdOption)
                .build()

            val result = credentialManager.getCredential(activityContext, request)
            val credential = result.credential

            val googleIdTokenCredential = GoogleIdTokenCredential.createFrom(credential.data)

            _authState.value = AuthState(
                isSignedIn = true,
                accessToken = googleIdTokenCredential.idToken,
                email = googleIdTokenCredential.id,
            )
        } catch (e: Exception) {
            _authState.value = AuthState(
                isSignedIn = false,
                error = e.message ?: "Sign-in failed",
            )
        }
    }

    fun signOut() {
        _authState.value = AuthState()
    }

    fun updateAccessToken(token: String) {
        _authState.value = _authState.value.copy(accessToken = token)
    }
}
