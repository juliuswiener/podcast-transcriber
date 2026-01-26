package com.transcriber.app.util

import android.content.Context
import android.content.SharedPreferences

object PreferencesManager {

    private const val PREFS_NAME = "voice_transcriber_prefs"
    private const val KEY_API_KEY = "openai_api_key"

    private fun getPreferences(context: Context): SharedPreferences {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    fun saveApiKey(context: Context, apiKey: String) {
        getPreferences(context).edit().putString(KEY_API_KEY, apiKey).apply()
    }

    fun getApiKey(context: Context): String {
        return getPreferences(context).getString(KEY_API_KEY, "") ?: ""
    }

    fun clearApiKey(context: Context) {
        getPreferences(context).edit().remove(KEY_API_KEY).apply()
    }
}
