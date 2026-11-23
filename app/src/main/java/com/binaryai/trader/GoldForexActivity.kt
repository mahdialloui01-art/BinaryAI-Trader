package com.binaryai.trader

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Color
import android.widget.*
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/** Standalone XAU/USD reference screen. It never calls Binary Options endpoints. */
class GoldForexActivity : Activity() {
    private val io = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val baseUrl by lazy {
        getSharedPreferences("binaryai", MODE_PRIVATE)
            .getString("base", "https://binaryai-trader-api.onrender.com")!!.trimEnd('/')
    }
    private lateinit var price: TextView
    private lateinit var info: TextView
    private lateinit var candles: TextView
    private val refreshLoop = object : Runnable {
        override fun run() { refresh(); handler.postDelayed(this, 15000L) }
    }

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
            text = "سوق الذهب مقابل الدولار • مصدر مستقل عن Deriv Binary Options"
            textSize = 12f; setTextColor(Color.rgb(60, 214, 177))
            setPadding(0, 8, 0, 18)
        })
        price = TextView(this).apply {
            text = "جاري تحميل سعر الذهب..."
            textSize = 30f; setTextColor(Color.WHITE); setPadding(0, 18, 0, 8)
        }
        root.addView(price)
        info = TextView(this).apply { textSize = 12f; setTextColor(Color.LTGRAY) }
        root.addView(info)
        root.addView(Button(this).apply {
            text = "تحديث السعر والشموع"; isAllCaps = false
            setOnClickListener { refresh() }
        })
        root.addView(TextView(this).apply {
            text = "شموع XAUUSD — آخر 1 دقيقة"
            textSize = 14f; setTextColor(Color.WHITE); setPadding(0, 20, 0, 10)
        })
        candles = TextView(this).apply {
            textSize = 12f; setTextColor(Color.rgb(190, 205, 224))
            typeface = android.graphics.Typeface.MONOSPACE
        }
        val scroll = ScrollView(this)
        scroll.addView(candles)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        root.addView(TextView(this).apply {
            text = "تنبيه: بيانات مرجعية قد تكون متأخرة ولا تضمن مطابقة سعر وسيطك. لا يوجد تنفيذ صفقات."
            textSize = 10f; setTextColor(Color.rgb(255, 194, 91)); setPadding(0, 14, 0, 0)
        })
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        handler.removeCallbacks(refreshLoop)
        refreshLoop.run()
    }

    override fun onPause() {
        handler.removeCallbacks(refreshLoop)
        super.onPause()
    }

    private fun refresh() {
        price.text = "جاري تحديث XAUUSD..."
        io.execute {
            try {
                val q = getJson("$baseUrl/forex/gold/quote")
                val c = getJson("$baseUrl/forex/gold/candles?interval=1m&limit=30")
                val rows = c.optJSONArray("candles")
                val lines = StringBuilder()
                if (rows != null) for (i in 0 until rows.length()) {
                    val row = rows.getJSONObject(i)
                    lines.append(row.optString("timestamp").take(19).replace("T", " "))
                        .append("  O ").append(row.optDouble("open"))
                        .append(" H ").append(row.optDouble("high"))
                        .append(" L ").append(row.optDouble("low"))
                        .append(" C ").append(row.optDouble("close")).append('\n')
                }
                runOnUiThread {
                    price.text = "XAUUSD  $ " + String.format(java.util.Locale.US, "%.2f", q.optDouble("price"))
                    info.text = "المصدر: Yahoo Finance • الحالة: " + q.optString("status") +
                        " • آخر تحديث UTC: " + q.optString("timestamp")
                    candles.text = lines.toString().ifBlank { "لا توجد شموع متاحة حالياً." }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    price.text = "تعذر جلب سعر الذهب"
                    info.text = e.message ?: "تحقق من اتصال الخادم."
                    candles.text = "أعد المحاولة لاحقاً."
                }
            }
        }
    }

    private fun getJson(address: String): JSONObject {
        val connection = URL(address).openConnection() as HttpURLConnection
        connection.connectTimeout = 12000
        connection.readTimeout = 15000
        connection.setRequestProperty("Accept", "application/json")
        return try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream.bufferedReader().use { it.readText() }
            if (code !in 200..299) throw IllegalStateException("HTTP $code: $body")
            JSONObject(body)
        } finally { connection.disconnect() }
    }
}
