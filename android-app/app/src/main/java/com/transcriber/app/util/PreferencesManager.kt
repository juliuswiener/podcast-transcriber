package com.transcriber.app.util

import android.content.Context
import android.content.SharedPreferences

object PreferencesManager {

    private const val PREFS_NAME = "voice_transcriber_prefs"
    private const val KEY_API_KEY = "openai_api_key"

    private fun getPreferences(context: Context): SharedPreferences {
        // Use applicationContext to ensure consistent preferences across activity lifecycle
        return context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    fun saveApiKey(context: Context, apiKey: String) {
        // Use commit() instead of apply() to ensure synchronous write
        getPreferences(context).edit().putString(KEY_API_KEY, apiKey).commit()
    }

    fun getApiKey(context: Context): String {
        return getPreferences(context).getString(KEY_API_KEY, "") ?: ""
    }

    fun clearApiKey(context: Context) {
        getPreferences(context).edit().remove(KEY_API_KEY).commit()
    }
}
