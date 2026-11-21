package com.binaryai.trader

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Color
import android.graphics.RectF
import android.view.Gravity
import android.view.View
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.Executors
import okhttp3.OkHttpClient
import okhttp3.Call
import okhttp3.Callback
import okhttp3.RequestBody
import okhttp3.Request
import okhttp3.Response
import java.util.concurrent.TimeUnit
import kotlin.math.max
import kotlin.math.min

class MainActivity : Activity() {
    private val io = Executors.newSingleThreadExecutor()
    private val liveHandler = Handler(Looper.getMainLooper())
    private var liveTickBusy = false
    private var liveCandlesBusy = false
    private var liveQualityBusy = false
    private val streamClient = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(0, TimeUnit.MILLISECONDS).build()
    private var streamCall: Call? = null
    private var streamConnected = false
    private var lastStreamTickAt = 0L
    private var streamReconnectPending = false
    private val streamReconnect = object : Runnable { override fun run() { streamReconnectPending = false; startTickStream() } }
    private var lastQualityPoll = 0L
    private val liveLoop = object : Runnable {
        override fun run() {
            pollLiveMarket()
            liveHandler.postDelayed(this, 10000L)
        }
    }
    private val bg = Color.rgb(8, 14, 27)
    private val panel = Color.rgb(17, 27, 44)
    private val muted = Color.rgb(139, 157, 181)
    private val mint = Color.rgb(60, 214, 177)
    private val red = Color.rgb(255, 105, 117)
    private lateinit var base: EditText
    private lateinit var symbol: EditText
    private lateinit var status: TextView
    private lateinit var page: LinearLayout
    private lateinit var nav: LinearLayout
    private lateinit var chart: CandleChartView
    private lateinit var priceText: TextView
    private lateinit var changeText: TextView
    private lateinit var marketText: TextView
    private lateinit var qualityText: TextView
    private var activePage = "home"
    private var lastCandles = JSONArray()
    private var lastTick = JSONObject()
    private var lastHealth = JSONObject()
    private var lastSymbols = JSONArray()
    private var lastHistory = JSONObject()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = bg
        window.navigationBarColor = bg
        val prefs = getSharedPreferences("binaryai", MODE_PRIVATE)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(bg)
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(18), dp(20), dp(8))
        }
        val brand = TextView(this).apply {
            text = "BINARYAI  /  TRADER"
            textSize = 21f; setTextColor(Color.WHITE); setTypeface(null, 1)
        }
        val tagline = TextView(this).apply {
            text = "منصة تحليل وأبحاث السوق  •  READ ONLY"
            textSize = 11f; setTextColor(mint); setPadding(0, dp(4), 0, dp(12))
        }
        status = TextView(this).apply {
            text = "● غير متصل بالخادم  |  التنفيذ معطّل"
            textSize = 11f; setTextColor(Color.rgb(255, 194, 91))
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setBackgroundColor(panel)
        }
        header.addView(brand); header.addView(tagline); header.addView(status)
        root.addView(header)
        val scroll = ScrollView(this).apply { isFillViewport = true }
        page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(22))
        }
        scroll.addView(page)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(6), dp(6), dp(6), dp(8))
            setBackgroundColor(Color.rgb(13, 22, 37))
        }
        root.addView(nav)
        setContentView(root)

        base = EditText(this).apply {
            hint = "رابط API على HTTPS"
            setSingleLine(true); textSize = 13f
            setTextColor(Color.WHITE); setHintTextColor(muted)
            setText(prefs.getString("base", "https://binaryai-trader-api.onrender.com") ?: "https://binaryai-trader-api.onrender.com")
            setPadding(dp(12), 0, dp(12), 0)
            setBackgroundColor(panel)
        }
        symbol = EditText(this).apply {
            hint = "الرمز مثل frxEURUSD"
            setSingleLine(true); textSize = 13f
            setTextColor(Color.WHITE); setHintTextColor(muted)
            setText(prefs.getString("symbol", "frxEURUSD") ?: "frxEURUSD")
            setPadding(dp(12), 0, dp(12), 0)
            setBackgroundColor(panel)
        }
        renderNav()
        showPage("home")
        if (base.text.isNotBlank()) connectAndRefresh()
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun label(text: String, size: Float = 12f, color: Int = muted, bold: Boolean = false) =
        TextView(this).apply {
            this.text = text; textSize = size; setTextColor(color)
            if (bold) setTypeface(null, 1)
        }

    private fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(14), dp(13), dp(14), dp(13))
        setBackgroundColor(panel)
    }

    private fun addGap(parent: LinearLayout, height: Int = 10) {
        parent.addView(View(this), LinearLayout.LayoutParams(1, dp(height)))
    }

    private fun addSection(parent: LinearLayout, title: String) {
        val t = label(title, 13f, Color.WHITE, true)
        t.setPadding(dp(2), dp(14), 0, dp(8))
        parent.addView(t)
    }

    private fun actionButton(text: String, action: () -> Unit): Button =
        Button(this).apply {
            this.text = text; textSize = 11f; isAllCaps = false
            setTextColor(Color.WHITE); setBackgroundColor(Color.rgb(25, 105, 104))
            setOnClickListener { action() }
        }

    private fun renderNav() {
        nav.removeAllViews()
        listOf("home" to "الرئيسية", "assets" to "الأصول", "lab" to "المختبر", "history" to "السجل").forEach { (key, title) ->
            val b = TextView(this).apply {
                text = title; gravity = Gravity.CENTER
                textSize = 12f; setTypeface(null, if (activePage == key) 1 else 0)
                setTextColor(if (activePage == key) mint else muted)
                setPadding(0, dp(10), 0, dp(10))
                setOnClickListener { activePage = key; renderNav(); showPage(key) }
            }
            nav.addView(b, LinearLayout.LayoutParams(0, dp(44), 1f))
        }
    }

    private fun showPage(which: String) {
        page.removeAllViews()
        when (which) {
            "home" -> buildHome()
            "assets" -> buildAssets()
            "lab" -> buildLab()
            "history" -> buildHistory()
        }
    }

    private fun buildHome() {
        addSection(page, "لوحة السوق")
        val settings = card()
        settings.addView(label("رابط خادم BinaryAI", 11f))
        (base.parent as? android.view.ViewGroup)?.removeView(base)
        settings.addView(base, LinearLayout.LayoutParams(-1, dp(48)))
        addGap(settings, 8)
        settings.addView(label("الأصل المختار", 11f))
        (symbol.parent as? android.view.ViewGroup)?.removeView(symbol)
        settings.addView(symbol, LinearLayout.LayoutParams(-1, dp(48)))
        addGap(settings, 8)
        settings.addView(actionButton("حفظ الإعدادات والاتصال") { 
            val url = base.text.toString().trim().trimEnd('/')
            if (!url.startsWith("https://")) { toast("أدخل رابط HTTPS صحيحاً"); return@actionButton }
            getSharedPreferences("binaryai", MODE_PRIVATE).edit()
                .putString("base", url).putString("symbol", safeSymbol()).apply()
            connectAndRefresh()
        })
        page.addView(settings)
        addGap(page)
        val quote = card()
        quote.addView(label("سعر Deriv المباشر — قراءة فقط", 11f))
        priceText = label("--", 30f, Color.WHITE, true)
        priceText.setPadding(0, dp(7), 0, dp(2))
        quote.addView(priceText)
        changeText = label("Bid: --     Ask: --", 12f, mint)
        quote.addView(changeText)
        marketText = label("المصدر: Deriv / Deriv  •  بانتظار البث", 10f)
        marketText.setPadding(0, dp(8), 0, 0)
        quote.addView(marketText)
        page.addView(quote)
        addGap(page)
        val chartCard = card()
        chartCard.addView(label("مخطط الشموع  |  1 دقيقة", 12f, Color.WHITE, true))
        chart = CandleChartView(this)
        chart.setBackgroundColor(panel)
        chartCard.addView(chart, LinearLayout.LayoutParams(-1, dp(220)))
        chartCard.addView(label("شموع Deriv لدفتر Deriv؛ قد توجد فروق أو تأخيرات لدى المزود والشبكة.", 10f))
        page.addView(chartCard)
        addGap(page)
        addSection(page, "جودة البيانات")
        val qualityCard = card()
        qualityText = label("لم يتم فحص حداثة البيانات بعد.", 11f, Color.WHITE)
        qualityCard.addView(qualityText)
        qualityCard.addView(actionButton("فحص جودة المصدر") { loadQuality() })
        page.addView(qualityCard)
        addGap(page)
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        actions.addView(actionButton("تحديث السوق") { refreshMarket() }, LinearLayout.LayoutParams(0, dp(48), 1f))
        actions.addView(actionButton("تحميل الأصول") { loadSymbols() }, LinearLayout.LayoutParams(0, dp(48), 1f))
        page.addView(actions)
        addSection(page, "قرار المحرك")
        val signal = card()
        signal.addView(label("NO TRADE", 20f, Color.rgb(255, 194, 91), true))
        signal.addView(label("لا توجد حالياً استراتيجية اجتازت التحقق التاريخي والاختبار الأمامي. لن نخترع إشارة CALL أو PUT.", 12f, Color.WHITE))
        page.addView(signal)
        addGap(page)
        page.addView(label("وضع البحث فقط • لا تسجيل دخول Deriv • لا تنفيذ صفقات • لا ضمان أرباح", 10f))
        if (lastTick.length() > 0) renderTick()
        if (lastCandles.length() > 0) chart.setCandles(lastCandles)
    }

    private fun buildAssets() {
        addSection(page, "كتالوج الأصول")
        page.addView(label("كل أصول Deriv المتاحة. اختيار الأصل يحمّل مخططه ويتحقق من عقود Binary Options فقط؛ لا يتم تنفيذ تداول فوركس.", 11f))
        addGap(page)
        page.addView(actionButton("تحديث قائمة الأصول") { loadSymbols() })
        addGap(page)
        if (lastSymbols.length() == 0) {
            page.addView(card().apply { addView(label("لم يتم تحميل الكتالوج بعد. اتصل بالخادم ثم اضغط تحديث.", 12f, Color.WHITE)) })
        } else {
            for (i in 0 until min(lastSymbols.length(), 250)) {
                val item = lastSymbols.optJSONObject(i) ?: continue
                val sym = item.optString("symbol", item.optString("name", item.optString("ticker", "UNKNOWN")))
                val isOtc = false
                val row = card()
                val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                top.addView(label(sym, 15f, Color.WHITE, true), LinearLayout.LayoutParams(0, -2, 1f))
                top.addView(label(item.optString("market_display_name", item.optString("market", "DERIV")), 10f, mint, true))
                row.addView(top)
                row.addView(label((if (item.optBoolean("exchange_is_open", false)) "مفتوح" else "مغلق") + " • " + item.optString("display_name", item.optString("name", "Deriv")) + " • اضغط لعرض المخطط", 10f))
                row.setOnClickListener {
                    symbol.setText(sym)
                    getSharedPreferences("binaryai", MODE_PRIVATE).edit().putString("symbol", sym).apply()
                    stopLiveStream()
                    activePage = "home"; renderNav(); showPage("home"); refreshMarket()
                }
                page.addView(row); addGap(page, 7)
            }
        }
    }

    private fun buildLab() {
        addSection(page, "مختبر الاستراتيجيات")
        val intro = card()
        intro.addView(label("اختبار تاريخي منضبط", 16f, Color.WHITE, true))
        intro.addView(label("يقيس المحرك الصفقات التي تقدمها له، ولا ينشئ حالياً استراتيجية دخول مستقلة. الاختبار يجب أن يكون زمنياً: تدريب ثم تحقق ثم اختبار لم يُستخدم في الضبط.", 12f, Color.WHITE))
        page.addView(intro)
        addGap(page)
        val noSignal = card()
        noSignal.addView(label("حالة الاستراتيجية", 12f))
        noSignal.addView(label("غير معتمدة  •  NO TRADE", 19f, Color.rgb(255,194,91), true))
        noSignal.addView(label("لن نعرض نسبة نجاح تقديرية. يلزم سجل شموع كافٍ، قواعد دخول محددة، مدة انتهاء، عائد payout، ثم اختبار خارج العينة واختبار أمامي.", 11f))
        page.addView(noSignal)
        addGap(page)
        page.addView(actionButton("قراءة إحصاءات التاريخ") { loadHistory() })
        addGap(page)
        page.addView(actionButton("جلب إشارة المحرك الحالية") { loadExampleSignal() })
        addGap(page)
        page.addView(label("مقاييس الاعتماد المطلوبة: عدد الصفقات، Win/Loss/Tie، صافي العائد بعد payout، expectancy، أقصى drawdown، أطول سلسلة خسائر، ونتائج الاختبار خارج العينة.", 11f))
    }

    private fun buildHistory() {
        addSection(page, "قاعدة البيانات التاريخية")
        page.addView(actionButton("تحديث إحصاءات التخزين") { loadHistory() })
        addGap(page)
        val stats = card()
        val count = lastHistory.optInt("stored_candles", 0)
        stats.addView(label("إجمالي الشموع المخزنة", 11f))
        stats.addView(label(count.toString(), 28f, Color.WHITE, true))
        stats.addView(label("Deriv: " + lastHistory.optInt("deriv_candles", 0), 12f, mint))
        page.addView(stats)
        addGap(page)
        val collect = card()
        collect.addView(label("جمع بيانات الأصل المختار", 13f, Color.WHITE, true))
        collect.addView(label("سيتم جلب حتى 500 شمعة 1m من Deriv وتخزينها في SQLite على الخادم.", 11f))
        addGap(collect, 8)
        collect.addView(actionButton("جمع 500 شمعة") { collectCandles() })
        page.addView(collect)
        addGap(page)
        page.addView(label("تنبيه: التخزين المحلي على استضافة مؤقتة قد يُمسح عند إعادة النشر ما لم يتم ربط قرص دائم.", 10f))
    }

    private fun connectAndRefresh() {
        stopLiveStream()
        request("/health") { obj, error ->
            if (obj != null) {
                lastHealth = obj
                status.text = "● الخادم متصل — نتحقق من تغذية Deriv"
                status.setTextColor(Color.rgb(255,194,91))
                loadDerivSymbols()
            } else {
                status.text = "● تعذر الاتصال بالخادم"
                status.setTextColor(red)
                toast(error ?: "فشل الاتصال")
            }
        }
    }

    private fun pollLiveMarket() {
        val age = if (lastStreamTickAt > 0L) System.currentTimeMillis() - lastStreamTickAt else Long.MAX_VALUE
        if (streamCall == null && !streamReconnectPending && lastSymbols.length() > 0) startTickStream()
        if (::status.isInitialized && streamConnected && age > 30000L) {
            status.text = "● لا توجد Tick منذ ${age / 1000}s رغم بقاء القناة"
            status.setTextColor(red)
        }
    }

    private fun loadDerivSymbols() {
        request("/binary-options/symbols") { obj, error ->
            if (obj == null) {
                status.text = "● تعذر تحميل كتالوج Deriv: ${error ?: "خطأ"}"
                status.setTextColor(red)
                return@request
            }
            lastSymbols = obj.optJSONArray("symbols") ?: JSONArray()
            if (lastSymbols.length() == 0) {
                status.text = "● كتالوج Deriv فارغ"
                status.setTextColor(red)
                return@request
            }
            val requested = safeSymbol()
            var chosen: JSONObject? = null
            for (i in 0 until lastSymbols.length()) {
                val item = lastSymbols.optJSONObject(i) ?: continue
                val id = item.optString("symbol")
                if (id.equals(requested, true) || id.equals(requested.removeSuffix("_otc"), true) || id.equals(requested + "_otc", true)) {
                    chosen = item; break
                }
            }
            if (chosen == null) chosen = (0 until lastSymbols.length()).mapNotNull { lastSymbols.optJSONObject(it) }.firstOrNull { it.optString("symbol").equals("1HZ100V", true) } ?: (0 until lastSymbols.length()).mapNotNull { lastSymbols.optJSONObject(it) }.firstOrNull { it.optBoolean("exchange_is_open", false) && (it.optString("market_display_name") + it.optString("market")).contains("synthetic", true) } ?: (0 until lastSymbols.length()).mapNotNull { lastSymbols.optJSONObject(it) }.firstOrNull { it.optBoolean("exchange_is_open", false) } ?: lastSymbols.optJSONObject(0)
            val exact = chosen?.optString("symbol").orEmpty()
            if (exact.isBlank()) {
                status.text = "● معرّف الرمز غير صالح"; status.setTextColor(red); return@request
            }
            symbol.setText(exact)
            getSharedPreferences("binaryai", MODE_PRIVATE).edit().putString("symbol", exact).apply()
            loadDerivCandles(exact)
            loadDerivContracts(exact)
            startTickStream()
        }
    }

    private fun startTickStream() {
        if (!::symbol.isInitialized || base.text.isBlank() || streamCall != null) return
        val selected = safeSymbol()
        val url = base.text.toString().trim().trimEnd('/') + "/deriv/stream?symbol=" + URLEncoder.encode(selected, "UTF-8")
        val req = Request.Builder().url(url).header("Accept", "text/event-stream").header("Cache-Control", "no-cache").build()
        runOnUiThread { if (::status.isInitialized) { status.text = "● جاري فتح بث Deriv: $selected"; status.setTextColor(Color.rgb(255,194,91)) } }
        val call = streamClient.newCall(req)
        streamCall = call
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: java.io.IOException) {
                streamCall = null; streamConnected = false
                runOnUiThread { if (::status.isInitialized) { status.text = "● فشل بث Deriv: ${e.message}"; status.setTextColor(red) } }
                scheduleStreamReconnect()
            }
            override fun onResponse(call: Call, response: Response) {
                if (!response.isSuccessful) {
                    val detail = response.body?.string().orEmpty().take(150)
                    val code = response.code
                    response.close(); streamCall = null; streamConnected = false
                    runOnUiThread { if (::status.isInitialized) { status.text = "● رفض بث Deriv HTTP $code: $detail"; status.setTextColor(red) } }
                    if (code != 401 && code != 403 && code != 429) scheduleStreamReconnect()
                    return
                }
                streamConnected = true
                runOnUiThread { if (::status.isInitialized) { status.text = "● قناة Deriv مفتوحة — انتظار تأكيد الاشتراك"; status.setTextColor(Color.rgb(255,194,91)) } }
                var eventName = ""
                try {
                    val source = response.body?.source() ?: throw java.io.IOException("Empty SSE body")
                    while (!call.isCanceled()) {
                        val line = source.readUtf8Line() ?: break
                        if (line.isBlank()) { eventName = ""; continue }
                        if (line.startsWith(":")) continue
                        if (line.startsWith("event:")) eventName = line.substringAfter("event:").trim()
                        else if (line.startsWith("data:")) {
                            val data = line.substringAfter("data:").trim()
                            when (eventName) {
                                "connected" -> runOnUiThread { if (::status.isInitialized) { status.text = "● Deriv أكد اشتراك $selected"; status.setTextColor(mint) } }
                                "tick" -> {
                                    val tick = JSONObject(data)
                                    if (tick.optString("symbol").equals(selected, true)) applyDerivTick(tick)
                                }
                                "error" -> {
                                    val detail = try { JSONObject(data).optString("error", "Deriv stream error") } catch (_: Exception) { data.take(120) }
                                    runOnUiThread { if (::status.isInitialized) { status.text = "● خطأ بث Deriv: $detail"; status.setTextColor(red) } }
                                }
                                "closed" -> runOnUiThread { if (::status.isInitialized) { status.text = "● الرمز $selected مغلق للتداول لدى Deriv"; status.setTextColor(Color.rgb(255,194,91)) } }
                                "replaced" -> runOnUiThread { if (::status.isInitialized) { status.text = "● استُبدل اتصال البث"; status.setTextColor(red) } }
                            }
                        }
                    }
                } catch (e: Exception) {
                    if (!call.isCanceled()) runOnUiThread { if (::status.isInitialized) { status.text = "● انقطع تدفق Deriv: ${e.message}"; status.setTextColor(red) } }
                } finally {
                    response.close()
                    if (streamCall === call) streamCall = null
                    streamConnected = false
                    if (!call.isCanceled()) scheduleStreamReconnect()
                }
            }
        })
    }

    private fun applyDerivTick(tick: JSONObject) {
        val price = tick.optDouble("price", Double.NaN)
        if (!price.isFinite()) return
        val epoch = tick.optLong("time", 0L)
        val stamp = if (epoch > 0L) java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US).apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }.format(java.util.Date(epoch * 1000L)) else ""
        lastStreamTickAt = System.currentTimeMillis()
        val normalized = JSONObject().put("provider", "deriv").put("symbol", tick.optString("symbol", safeSymbol())).put("price", price).put("mid", price).put("timestamp", stamp).put("stale", false).put("stream", "deriv_sse")
        runOnUiThread {
            lastTick = normalized
            if (::marketText.isInitialized && activePage == "home") renderTick()
            if (::status.isInitialized) { status.text = "● Tick Deriv حي — ${tick.optString("symbol", safeSymbol())} — ${stamp.ifBlank { "وقت المزود غير متاح" }}"; status.setTextColor(mint) }
            updateLiveCandle(price, stamp)
        }
    }

    private fun loadDerivContracts(selected: String) {
        val encoded = URLEncoder.encode(selected, "UTF-8")
        request("/binary-options/$encoded/contracts") { obj, error ->
            if (obj != null) {
                val contracts = obj.optJSONArray("available") ?: JSONArray()
                val names = ArrayList<String>()
                for (i in 0 until contracts.length()) {
                    val item = contracts.optJSONObject(i) ?: continue
                    val label = item.optString("contract_display", item.optString("contract_type", item.optString("contract_category", "")))
                    if (label.isNotBlank()) names.add(label)
                }
                if (::status.isInitialized && names.isEmpty()) {
                    status.text = "● $selected: لا توجد عقود Binary Options متاحة حالياً"
                    status.setTextColor(Color.rgb(255,194,91))
                } else if (::status.isInitialized) {
                    status.text = "● $selected: ${names.size} أنواع Binary Options متاحة على Deriv"
                    status.setTextColor(mint)
                }
            } else if (::status.isInitialized) {
                status.text = "● تعذر التحقق من عقود الخيارات: ${error ?: "خطأ"}"
                status.setTextColor(red)
            }
        }
    }

    private fun loadDerivCandles(selected: String) {
        val encoded = URLEncoder.encode(selected, "UTF-8")
        request("/market/$encoded/candles?interval=1m&limit=100") { obj, error ->
            if (obj != null) {
                lastCandles = normalizeDerivCandles(obj.optJSONArray("candles") ?: JSONArray())
                if (activePage == "home" && ::chart.isInitialized) chart.setCandles(lastCandles)
            } else if (::status.isInitialized) {
                status.text = "● تعذر تحميل شموع Deriv: ${error ?: "خطأ"}"; status.setTextColor(Color.rgb(255,194,91))
            }
        }
    }

    private fun normalizeDerivCandles(rows: JSONArray): JSONArray {
        val result = JSONArray()
        for (i in 0 until rows.length()) {
            val row = rows.optJSONObject(i) ?: continue
            val copy = JSONObject(row.toString())
            val epoch = row.optLong("time", 0L)
            if (epoch > 0L) copy.put("openTime", java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US).apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }.format(java.util.Date(epoch * 1000L)))
            result.put(copy)
        }
        return result
    }

    private fun scheduleStreamReconnect() {
        if (!streamReconnectPending && !isFinishing) { streamReconnectPending = true; liveHandler.postDelayed(streamReconnect, 5000L) }
    }

    private fun stopLiveStream() {
        liveHandler.removeCallbacks(streamReconnect); streamReconnectPending = false
        streamCall?.cancel(); streamCall = null; streamConnected = false
    }

    private fun startLiveUpdates() {
        liveHandler.removeCallbacks(liveLoop); liveHandler.post(liveLoop)
        if (streamCall == null && lastSymbols.length() > 0) startTickStream()
    }

    private fun stopLiveUpdates() {
        liveHandler.removeCallbacks(liveLoop); stopLiveStream()
    }

    private fun updateLiveCandle(price: Double, timestamp: String) {
        val parser = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US).apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }
        val tickTime = try { parser.parse(timestamp.take(19))?.time ?: System.currentTimeMillis() } catch (_: Exception) { System.currentTimeMillis() }
        val bucket = tickTime / 60000L * 60000L
        val openTime = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US).apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }.format(java.util.Date(bucket))
        val lastIndex = lastCandles.length() - 1
        val last = if (lastIndex >= 0) lastCandles.optJSONObject(lastIndex) else null
        val lastTime = last?.optString("openTime")?.takeIf { it.isNotBlank() } ?: last?.optString("timestamp") ?: ""
        val lastBucket = try { parser.parse(lastTime.take(19))?.time?.div(60000L)?.times(60000L) ?: -1L } catch (_: Exception) { -1L }
        if (last == null || lastBucket != bucket) {
            val candle = JSONObject().put("openTime", openTime).put("open", price).put("high", price)
                .put("low", price).put("close", price).put("isOpen", true).put("tickVolume", 1)
            lastCandles.put(candle)
            while (lastCandles.length() > 300) lastCandles.remove(0)
        } else {
            last.put("high", max(last.optDouble("high", price), price))
            last.put("low", min(last.optDouble("low", price), price))
            last.put("close", price).put("isOpen", true).put("tickVolume", last.optInt("tickVolume", 0) + 1)
        }
        if (activePage == "home" && ::chart.isInitialized) chart.setCandles(lastCandles)
    }

    private fun refreshMarket() {
        if (lastSymbols.length() == 0) loadDerivSymbols()
        else { loadDerivCandles(safeSymbol()); if (streamCall == null) startTickStream() }
    }

    private fun loadQuality() {
        val age = if (lastStreamTickAt > 0L) (System.currentTimeMillis() - lastStreamTickAt) / 1000L else -1L
        val state = when {
            !streamConnected -> "البث غير متصل"
            age < 0L -> "القناة مفتوحة ولم تصل أول Tick"
            age > 30L -> "السعر متوقف منذ $age ثانية"
            else -> "بث Deriv مستمر — آخر Tick منذ $age ثانية"
        }
        if (::qualityText.isInitialized) qualityText.text = "المصدر: Deriv / Deriv\nالحالة: $state\nالرمز: ${safeSymbol()}\nعدد الشموع المعروضة: ${lastCandles.length()}"
    }

    private fun renderTick() {
        if (!::priceText.isInitialized) return
        val mid = lastTick.opt("mid")
        val bid = lastTick.opt("bid")
        val ask = lastTick.opt("ask")
        priceText.text = if (mid == null || mid == JSONObject.NULL) "--" else mid.toString()
        changeText.text = "Bid: ${display(bid)}     Ask: ${display(ask)}"
        val stale = lastTick.optBoolean("stale", false)
        val source = if (lastTick.optString("stream") == "deriv_sse") "بث SSE مباشر" else "لا يوجد بث حي"
        marketText.text = "Deriv / Deriv  •  $source  •  ${if (stale) "بيانات قديمة" else "آخر تحديث: " + lastTick.optString("timestamp", "--")}"
        marketText.setTextColor(if (stale) red else muted)
    }

    private fun loadSymbols() {
        request("/binary-options/symbols") { obj, error ->
            if (obj != null) {
                lastSymbols = obj.optJSONArray("symbols") ?: JSONArray()
                if (activePage == "assets") showPage("assets")
                toast("تم تحميل ${lastSymbols.length()} أصل من Deriv")
            } else toast(error ?: "فشل تحميل رموز Deriv")
        }
    }

    private fun loadHistory() {
        request("/history/stats") { obj, error ->
            if (obj != null) { lastHistory = obj; if (activePage == "history" || activePage == "lab") showPage(activePage) }
            else toast(error ?: "تعذر قراءة السجل")
        }
    }

    private fun collectCandles() {
        request("/collect/${encodedSymbol()}/candles?interval=1m&limit=500", method = "POST") { obj, error ->
            if (obj != null) toast("تم حفظ ${obj.optInt("stored", 0)} شمعة")
            else toast(error ?: "فشل جمع البيانات")
        }
    }

    private fun loadExampleSignal() {
        request("/signals/example") { obj, error ->
            if (obj != null) {
                val decision = obj.optString("decision", "NO_TRADE")
                toast("قرار المحرك: $decision")
            } else toast(error ?: "تعذر جلب القرار")
        }
    }

    private fun request(path: String, method: String = "GET", done: (JSONObject?, String?) -> Unit) {
        val root = base.text.toString().trim().trimEnd('/')
        if (!root.startsWith("https://")) { toast("أدخل رابط API HTTPS أولاً"); return }
        io.execute {
            var conn: HttpURLConnection? = null
            try {
                conn = (URL(root + path).openConnection() as HttpURLConnection).apply {
                    requestMethod = method
                    connectTimeout = 15000; readTimeout = 20000
                    setRequestProperty("Accept", "application/json")
                }
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val body = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
                val parsed = if (code in 200..299) JSONObject(body) else null
                val err = if (parsed == null) "HTTP $code: " + body.take(180) else null
                runOnUiThread { done(parsed, err) }
            } catch (e: Exception) {
                runOnUiThread { done(null, e.message ?: "Network error") }
            } finally { conn?.disconnect() }
        }
    }

    private fun extractCandles(obj: JSONObject): JSONArray {
        val bars = obj.optJSONArray("candles") ?: obj.optJSONArray("bars") ?: JSONArray()
        return bars
    }

    private fun safeSymbol() = symbol.text.toString().trim().ifBlank { "1HZ100V" }
    private fun encodedSymbol() = URLEncoder.encode(safeSymbol(), "UTF-8")
    private fun display(v: Any?): String = if (v == null || v == JSONObject.NULL) "--" else v.toString()
    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()

    override fun onResume() {
        super.onResume()
        startLiveUpdates()
    }

    override fun onPause() {
        stopLiveUpdates()
        super.onPause()
    }

    override fun onDestroy() {
        stopLiveUpdates()
        io.shutdown()
        super.onDestroy()
    }
}

private class CandleChartView(context: android.content.Context) : View(context) {
    private val candles = ArrayList<DoubleArray>()
    private val grid = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(43, 57, 76); strokeWidth = 1f }
    private val wick = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 2f; strokeCap = Paint.Cap.ROUND }
    private val body = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(139,157,181); textSize = 10f }
    fun setCandles(rows: JSONArray) {
        candles.clear()
        for (i in 0 until rows.length()) {
            val o = rows.optJSONObject(i) ?: continue
            val open = number(o, "open") ?: number(o, "o") ?: continue
            val high = number(o, "high") ?: number(o, "h") ?: continue
            val low = number(o, "low") ?: number(o, "l") ?: continue
            val close = number(o, "close") ?: number(o, "c") ?: continue
            candles.add(doubleArrayOf(open, high, low, close))
        }
        invalidate()
    }
    private fun number(o: JSONObject, key: String): Double? {
        val v = o.opt(key)
        return when (v) {
            null, JSONObject.NULL -> null
            is Number -> v.toDouble()
            else -> v.toString().toDoubleOrNull()
        }
    }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val left = 12f; val right = width - 48f; val top = 18f; val bottom = height - 20f
        for (i in 0..4) {
            val y = top + (bottom - top) * i / 4f
            canvas.drawLine(left, y, right, y, grid)
        }
        if (candles.isEmpty()) {
            text.textSize = 12f
            canvas.drawText("لا توجد شموع محمّلة", left + 8, height / 2f, text)
            return
        }
        val visible = candles.takeLast(70)
        var lo = visible.minOf { it[2] }
        var hi = visible.maxOf { it[1] }
        if (hi <= lo) { hi += 1.0; lo -= 1.0 }
        val pad = (hi - lo) * 0.08
        lo -= pad; hi += pad
        fun y(v: Double) = (bottom - ((v - lo) / (hi - lo) * (bottom - top))).toFloat()
        val slot = (right - left) / visible.size
        val bodyW = max(2f, slot * 0.58f)
        visible.forEachIndexed { i, c ->
            val x = left + slot * (i + 0.5f)
            val up = c[3] >= c[0]
            val color = if (up) Color.rgb(60,214,177) else Color.rgb(255,105,117)
            wick.color = color; body.color = color
            canvas.drawLine(x, y(c[1]), x, y(c[2]), wick)
            val y1 = y(max(c[0], c[3])); val y2 = y(min(c[0], c[3]))
            val rect = RectF(x - bodyW/2, y1, x + bodyW/2, max(y1 + 2f, y2))
            canvas.drawRect(rect, body)
        }
        text.textSize = 9f
        canvas.drawText(String.format("%.5f", hi), right + 3, top + 4, text)
        canvas.drawText(String.format("%.5f", lo), right + 3, bottom, text)
    }
}
