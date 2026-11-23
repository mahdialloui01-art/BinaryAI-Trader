package com.binaryai.trader

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Color
import android.view.View
import android.widget.*
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import kotlin.math.max
import kotlin.math.min

/** Standalone XAU/USD Forex screen using the same Deriv live tick source as Binary Options. */
class GoldForexActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var streamCall: Call? = null
    private var historyCall: Call? = null
    private var reconnectPending = false
    private val reconnect = object : Runnable {
        override fun run() { reconnectPending = false; startStream() }
    }
    private val baseUrl by lazy {
        getSharedPreferences("binaryai", MODE_PRIVATE)
            .getString("base", "https://binaryai-trader-api.onrender.com")!!.trimEnd('/')
    }
    private lateinit var price: TextView
    private lateinit var info: TextView
    private lateinit var chart: CandleChartView
    private lateinit var candles: JSONArray
    private var lastTickAt = 0L
    private var selectedSymbol = "frxXAUUSD"
    private val green = Color.rgb(60, 214, 177)
    private val red = Color.rgb(255, 105, 117)
    private val muted = Color.rgb(139, 157, 181)
    private val panel = Color.rgb(17, 27, 44)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(8, 14, 27)
        window.navigationBarColor = Color.rgb(8, 14, 27)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(22, 24, 22, 20)
            setBackgroundColor(Color.rgb(8, 14, 27))
        }
        root.addView(TextView(this).apply {
            text = "FOREX GOLD  /  XAUUSD"
            textSize = 20f; setTextColor(Color.WHITE); setTypeface(null, 1)
        })
        root.addView(TextView(this).apply {
            text = "بث Deriv الحي • نفس مصدر أسعار الباينري أوبشن"
            textSize = 12f; setTextColor(green); setPadding(0, 8, 0, 18)
        })
        price = TextView(this).apply {
            text = "بانتظار أول Tick من Deriv..."
            textSize = 30f; setTextColor(Color.WHITE); setPadding(0, 18, 0, 8)
        }
        root.addView(price)
        info = TextView(this).apply {
            text = "● جاري الاتصال بقناة الذهب"
            textSize = 12f; setTextColor(Color.rgb(255, 194, 91))
        }
        root.addView(info)
        root.addView(Button(this).apply {
            text = "إعادة الاتصال بالبث الحي"; isAllCaps = false
            setOnClickListener {
                stopStream()
                startStream()
                loadCandles()
            }
        })
        root.addView(TextView(this).apply {
            text = "مخطط الشموع الحي — إطار دقيقة"
            textSize = 14f; setTextColor(Color.WHITE); setPadding(0, 20, 0, 10)
        })
        chart = CandleChartView(this).apply { setBackgroundColor(panel) }
        root.addView(chart, LinearLayout.LayoutParams(-1, dp(260)))
        root.addView(TextView(this).apply {
            text = "الشمعة الحالية تتحدث مع كل Tick من Deriv. إذا كان سوق الذهب مغلقاً أو الرمز غير متاح، سيظهر ذلك دون التحويل إلى مصدر آخر."
            textSize = 10f; setTextColor(muted); setPadding(0, 14, 0, 0)
        })
        root.addView(TextView(this).apply {
            text = "قراءة فقط • لا تنفيذ صفقات فوركس • سعر Deriv قد يختلف عن وسيط آخر"
            textSize = 10f; setTextColor(Color.rgb(255, 194, 91)); setPadding(0, 8, 0, 0)
        })
        setContentView(root)
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    override fun onResume() {
        super.onResume()
        loadCandles()
        startStream()
    }

    override fun onPause() {
        stopStream()
        historyCall?.cancel()
        historyCall = null
        super.onPause()
    }

    private fun loadCandles() {
        val request = Request.Builder()
            .url("$baseUrl/forex/gold/candles?interval=1m&limit=100")
            .get().build()
        val call = http.newCall(request)
        historyCall = call
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { info.text = "تعذر تحميل تاريخ شموع Deriv: " + (e.message ?: "network error") }
            }
            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string().orEmpty()
                response.close()
                if (!response.isSuccessful) {
                    runOnUiThread { info.text = "تعذر تحميل شموع الذهب — HTTP ${response.code}: " + body.take(120) }
                    return
                }
                try {
                    val json = JSONObject(body)
                    val rows = json.optJSONArray("candles") ?: JSONArray()
                    runOnUiThread {
                        selectedSymbol = json.optString("symbol", selectedSymbol)
                        candles = rows
                        chart.setCandles(candles)
                        info.text = "المصدر: Deriv • الرمز: $selectedSymbol • تم تحميل ${rows.length()} شمعة"
                        info.setTextColor(green)
                    }
                } catch (e: Exception) {
                    runOnUiThread { info.text = "صيغة شموع Deriv غير متوقعة: " + (e.message ?: "") }
                }
            }
        })
    }

    private fun startStream() {
        if (streamCall != null || isFinishing) return
        val request = Request.Builder()
            .url("$baseUrl/forex/gold/stream")
            .header("Accept", "text/event-stream")
            .header("Cache-Control", "no-cache")
            .build()
        info.text = "● جاري فتح بث الذهب من Deriv..."
        info.setTextColor(Color.rgb(255, 194, 91))
        val call = http.newCall(request)
        streamCall = call
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (streamCall === call) streamCall = null
                if (!call.isCanceled()) {
                    runOnUiThread {
                        info.text = "● انقطع بث Deriv: " + (e.message ?: "network error")
                        info.setTextColor(red)
                    }
                    scheduleReconnect()
                }
            }

            override fun onResponse(call: Call, response: Response) {
                if (!response.isSuccessful) {
                    val detail = response.body?.string().orEmpty().take(160)
                    val code = response.code
                    response.close()
                    if (streamCall === call) streamCall = null
                    runOnUiThread {
                        info.text = "● تعذر فتح بث الذهب HTTP $code: $detail"
                        info.setTextColor(red)
                    }
                    if (code != 401 && code != 403 && code != 429) scheduleReconnect()
                    return
                }
                try {
                    val source = response.body?.source() ?: throw IOException("Empty Deriv stream")
                    var eventName = ""
                    while (!call.isCanceled()) {
                        val line = source.readUtf8Line() ?: break
                        if (line.isBlank()) { eventName = ""; continue }
                        if (line.startsWith(":")) continue
                        if (line.startsWith("event:")) eventName = line.substringAfter("event:").trim()
                        else if (line.startsWith("data:")) {
                            val data = line.substringAfter("data:").trim()
                            when (eventName) {
                                "status" -> {
                                    val state = JSONObject(data)
                                    selectedSymbol = state.optString("symbol", selectedSymbol)
                                    runOnUiThread {
                                        info.text = "● قناة Deriv مفتوحة — $selectedSymbol — بانتظار Tick"
                                        info.setTextColor(Color.rgb(255, 194, 91))
                                    }
                                }
                                "tick" -> {
                                    val tick = JSONObject(data)
                                    if (tick.optString("symbol", selectedSymbol).equals(selectedSymbol, true)) {
                                        applyTick(tick)
                                    }
                                }
                                "error" -> {
                                    val detail = JSONObject(data).optString("error", "Deriv stream error")
                                    runOnUiThread {
                                        info.text = "● خطأ بث Deriv: $detail"
                                        info.setTextColor(red)
                                    }
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    if (!call.isCanceled()) runOnUiThread {
                        info.text = "● انقطع تدفق الذهب: " + (e.message ?: "")
                        info.setTextColor(red)
                    }
                } finally {
                    response.close()
                    if (streamCall === call) streamCall = null
                    if (!call.isCanceled()) scheduleReconnect()
                }
            }
        })
    }

    private fun applyTick(tick: JSONObject) {
        val value = tick.optDouble("price", Double.NaN)
        if (!value.isFinite()) return
        val epoch = tick.optLong("time", 0L)
        val timestamp = tick.optString("timestamp").ifBlank {
            if (epoch > 0L) java.time.Instant.ofEpochSecond(epoch).toString() else ""
        }
        lastTickAt = System.currentTimeMillis()
        runOnUiThread {
            price.text = "XAUUSD  $ " + String.format(java.util.Locale.US, "%.3f", value)
            info.text = "● بث Deriv حي • $selectedSymbol • ${timestamp.ifBlank { "وقت المزود غير متاح" }}"
            info.setTextColor(green)
            updateLiveCandle(value, epoch)
        }
    }

    private fun updateLiveCandle(value: Double, epoch: Long) {
        if (!::chart.isInitialized) return
        if (!::candles.isInitialized) candles = JSONArray()
        val millis = if (epoch > 0L) epoch * 1000L else System.currentTimeMillis()
        val bucket = millis / 60000L * 60000L
        val formatter = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US)
            .apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }
        val openTime = formatter.format(java.util.Date(bucket))
        val lastIndex = candles.length() - 1
        val last = if (lastIndex >= 0) candles.optJSONObject(lastIndex) else null
        val lastTime = last?.optString("openTime")?.takeIf { it.isNotBlank() }
            ?: last?.optString("timestamp").orEmpty()
        val parser = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US)
            .apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }
        val lastBucket = try {
            parser.parse(lastTime.take(19))?.time?.div(60000L)?.times(60000L) ?: -1L
        } catch (_: Exception) { -1L }

        if (last == null || lastBucket != bucket) {
            candles.put(JSONObject().put("openTime", openTime).put("timestamp", openTime)
                .put("open", value).put("high", value).put("low", value).put("close", value)
                .put("isOpen", true).put("tickVolume", 1))
            while (candles.length() > 300) candles.remove(0)
        } else {
            last.put("high", max(last.optDouble("high", value), value))
            last.put("low", min(last.optDouble("low", value), value))
            last.put("close", value).put("isOpen", true)
            last.put("tickVolume", last.optInt("tickVolume", 0) + 1)
        }
        chart.setCandles(candles)
    }

    private fun scheduleReconnect() {
        if (!reconnectPending && !isFinishing) {
            reconnectPending = true
            handler.postDelayed(reconnect, 5000L)
        }
    }

    private fun stopStream() {
        handler.removeCallbacks(reconnect)
        reconnectPending = false
        streamCall?.cancel()
        streamCall = null
    }
}
