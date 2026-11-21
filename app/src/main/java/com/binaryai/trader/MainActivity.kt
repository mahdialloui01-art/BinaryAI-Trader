package com.binaryai.trader

import android.app.Activity
import android.os.Bundle
import android.graphics.Color
import android.view.Gravity
import android.widget.*
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var base: EditText
    private lateinit var symbol: EditText
    private lateinit var output: TextView
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(9, 15, 28)
        window.navigationBarColor = Color.rgb(9, 15, 28)
        val prefs = getSharedPreferences("binaryai", MODE_PRIVATE)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(22, 26, 22, 20)
            setBackgroundColor(Color.rgb(9, 15, 28))
        }
        val scroll = ScrollView(this)
        val content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val heading = TextView(this).apply {
            text = "BinaryAI  /  TRADER"
            textSize = 25f; setTextColor(Color.WHITE); gravity = Gravity.CENTER_VERTICAL
        }
        val sub = TextView(this).apply {
            text = "READ-ONLY MARKET RESEARCH"
            textSize = 11f; setTextColor(Color.rgb(74, 211, 177)); setPadding(0, 5, 0, 18)
        }
        base = EditText(this).apply {
            hint = "Backend URL e.g. https://your-api.onrender.com"
            setSingleLine(true); setTextColor(Color.WHITE); setHintTextColor(Color.GRAY)
            setText(prefs.getString("base", "") ?: "")
            setPadding(14, 8, 14, 8)
        }
        symbol = EditText(this).apply {
            hint = "Symbol (e.g. EURUSD)"
            setSingleLine(true); setTextColor(Color.WHITE); setHintTextColor(Color.GRAY)
            setText("EURUSD"); setPadding(14, 8, 14, 8)
        }
        status = TextView(this).apply {
            text = "API: not connected  •  Execution: disabled"
            textSize = 12f; setTextColor(Color.rgb(255, 196, 92)); setPadding(0, 12, 0, 12)
        }
        output = TextView(this).apply {
            text = "Connect your own deployed BinaryAI API to load market data.\n\nThis app does not place trades."
            textSize = 13f; setTextColor(Color.rgb(220, 229, 242)); setPadding(14, 18, 14, 18)
            setBackgroundColor(Color.rgb(18, 28, 45))
        }
        content.addView(heading); content.addView(sub)
        addLabel(content, "BACKEND API"); content.addView(base, fieldParams())
        addLabel(content, "MARKET SYMBOL"); content.addView(symbol, fieldParams())
        val save = makeButton("SAVE API SETTINGS") {
            val b = base.text.toString().trim().trimEnd('/')
            prefs.edit().putString("base", b).apply()
            status.text = "API URL saved  •  Execution: disabled"
            status.setTextColor(Color.rgb(74, 211, 177))
            request("/health", "Checking API health…", true)
        }
        content.addView(save, buttonParams())
        addLabel(content, "MARKET DATA")
        val row1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row1.addView(makeButton("HEALTH") { request("/health", "Checking service…", true) }, rowButtonParams())
        row1.addView(makeButton("SYMBOLS") { request("/symbols", "Loading symbol catalogue…", false) }, rowButtonParams())
        content.addView(row1)
        val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row2.addView(makeButton("LIVE TICK") { request("/market/${safeSymbol()}/tick", "Loading latest reference tick…", false) }, rowButtonParams())
        row2.addView(makeButton("1M CANDLES") { request("/market/${safeSymbol()}/candles?interval=1m&limit=100", "Loading candles…", false) }, rowButtonParams())
        content.addView(row2)
        content.addView(makeButton("HISTORY STATS") { request("/history/stats", "Loading stored history…", false) }, buttonParams())
        addLabel(content, "API RESPONSE"); content.addView(output, LinearLayout.LayoutParams(-1, -2))
        val foot = TextView(this).apply {
            text = "\nResearch mode only. CALL/PUT examples are not validated signals. No Quotex login, order execution, or profit guarantee."
            textSize = 11f; setTextColor(Color.rgb(145, 160, 181))
        }
        content.addView(foot)
        scroll.addView(content); root.addView(scroll); setContentView(root)
        if (base.text.isNotBlank()) request("/health", "Checking saved API…", true)
    }

    private fun safeSymbol() = symbol.text.toString().trim().uppercase().ifBlank { "EURUSD" }
    private fun addLabel(parent: LinearLayout, value: String) {
        parent.addView(TextView(this).apply {
            text = value; textSize = 11f; setTextColor(Color.rgb(120, 145, 177))
            setPadding(0, 16, 0, 6)
        })
    }
    private fun fieldParams() = LinearLayout.LayoutParams(-1, 52).apply { bottomMargin = 8 }
    private fun buttonParams() = LinearLayout.LayoutParams(-1, 48).apply { topMargin = 7; bottomMargin = 7 }
    private fun rowButtonParams() = LinearLayout.LayoutParams(0, 48, 1f).apply { marginEnd = 6; topMargin = 5; bottomMargin = 5 }
    private fun makeButton(label: String, action: () -> Unit) = Button(this).apply {
        text = label; textSize = 11f; setTextColor(Color.WHITE)
        setBackgroundColor(Color.rgb(24, 102, 104)); setOnClickListener { action() }
    }
    private fun request(path: String, loading: String, isHealth: Boolean) {
        val b = base.text.toString().trim().trimEnd('/')
        if (b.isBlank() || !b.startsWith("https://")) {
            output.text = "Enter and save your deployed HTTPS API URL first.\nExample: https://your-service.onrender.com"
            status.text = "API URL required"; return
        }
        output.text = loading
        io.execute {
            try {
                val conn = (URL(b + path).openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"; connectTimeout = 12000; readTimeout = 15000
                    setRequestProperty("Accept", "application/json")
                }
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val body = stream?.bufferedReader()?.use { it.readText() } ?: "(empty response)"
                conn.disconnect()
                runOnUiThread {
                    output.text = "HTTP $code\n\n" + body.take(14000)
                    if (isHealth && code in 200..299) {
                        status.text = "API connected  •  Research only  •  Execution disabled"
                        status.setTextColor(Color.rgb(74, 211, 177))
                    } else if (code !in 200..299) {
                        status.text = "API response error: HTTP $code"
                        status.setTextColor(Color.rgb(255, 120, 120))
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    output.text = "Connection failed: ${e.message}\n\nCheck the HTTPS URL and confirm that the backend is deployed and awake."
                    status.text = "API unavailable"; status.setTextColor(Color.rgb(255, 196, 92))
                }
            }
        }
    }
}
