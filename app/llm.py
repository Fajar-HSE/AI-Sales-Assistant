import datetime
import json
import logging

from . import config

log = logging.getLogger("sai")

try:
    from groq import Groq
except Exception:
    Groq = None

ASSESSMENT_PROMPT = """Anda adalah AI Sales Assistant profesional untuk perusahaan training & sertifikasi (ICC Holding).
Tugas: analisis pesan customer → skor 6 komponen (0-100 tiap) + label.
Komponen:
1. Intent Signal (niat beli/tanya harga/daftar)
2. Product Match (kesesuaian produk yg ditawarkan)
3. Timeline Urgency (urgen/bulan ini/belum tentu)
4. Engagement Level (balas cepat/panjang/pendek)
5. Chat History Depth (baru/ada riwayat)
6. Decision Maker Authority (pemutus/ pengaruh/ staff)

Output HANYA JSON (tanpa teks lain):
{{"intent": 0-100, "product_match": 0-100, "urgency": 0-100, "sentiment": 0-100,
"chat_history": 0-100, "decision_maker": 0-100, "intent_label": "...",
"product": "...", "urgency_label": "...", "sentiment_label": "...",
"customer_stage": "..."}}

Pesan customer: {message}
Riwayat chat: {chat_history}"""

REPLY_PROMPT = """Anda Sales Assistant senior ICC Holding (LSP BNSP terakreditasi). Produk: POPAL, GIS/Geomatika, Sertifikasi BNSP, Pelatihan K3 (AK3, H2S, Confined Space, Working at Height), ISO, Manajemen Proyek.

Customer: {customer_name}
Pesan terbaru: {message}
Riwayat chat:
{chat_history}
Produk: {product}
Stage: {stage}
Score: {score}

ATURAN:
1. Jawab berdasarkan riwayat chat + pesan terbaru (lanjutkan percakapan, JANGAN ulangi sapaan/pertanyaan yang sudah dijawab)
2. Jawab spesifik + tanyakan data yang belum ada: jumlah peserta, lokasi, timeline, skema
3. Harga: range/estimasi saja (jangan final tanpa konteks)
4. Cross-sell cerdas: POPAL+TOT, K3+Sertif BNSP K3, GIS+Surveyor, Corporate Package
5. Value prop: LSP BNSP langsung, sertifikat resmi database nasional, compliance UU/PP/Kemenaker
6. Tone: konsultatif partner solusi, emoji max 2, bahasa Indonesia

Knowledge: {knowledge_chunks}

Output HANYA JSON:
{{"suggested_reply":"...", "confidence_score":0-100, "sources":[{{"type":"faq|sop|product|regulation","reference":"..."}}], "fallback":"..."}}
"""


def _to_int(v, default=50):
    try:
        return int(float(v))
    except Exception:
        return default


def _esc(s):
    if not s:
        return ""
    s = str(s)
    return s.replace("{", "{{").replace("}", "}}")


class GroqClient:
    def __init__(self, api_key: str = None):
        key = api_key or config.GROQ_API_KEY
        self.client = Groq(api_key=key) if (key and Groq) else None
        self.available = self.client is not None
        self.api_key = key

    def _chat_json(self, system: str, user: str, timeout: int = 30) -> dict:
        if not self.available:
            raise RuntimeError("groq not configured")
        resp = self.client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "system", "content": system + " Output in JSON format."},
                      {"role": "user", "content": user}],
            temperature=0.3, max_tokens=800, top_p=0.9,
            response_format={"type": "json_object"},
            timeout=timeout,
        )
        content = resp.choices[0].message.content
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            log.warning("Groq JSON decode error: %s | content: %s", e, content[:500])
            raise

    @staticmethod
    def _classify_intent(text: str) -> dict:
        t = text.lower()
        if any(w in t for w in ["harga", "biaya", "berapa", "modal", "tarif"]):
            return {"intent": 80, "label": "Minta informasi"}
        if any(w in t for w in ["jadwal", "kapan", "waktu", "tanggal"]):
            return {"intent": 70, "label": "Tanya jadwal"}
        if any(w in t for w in ["sertifikat", "skema", "bnsp", "asesor"]):
            return {"intent": 75, "label": "Tanya sertifikasi"}
        if any(w in t for w in ["promo", "diskon", "daftar", "registrasi", "penawaran"]):
            return {"intent": 85, "label": "Mau promo/daftar"}
        return {"intent": 50, "label": "General question"}

    def analyze(self, message: str, chat_history: str = "") -> dict:
        try:
            comps = self._chat_json(
                "Anda adalah AI Sales Assistant profesional. Output in JSON format.",
                ASSESSMENT_PROMPT.format(message=_esc(message[:2000]),
                                         chat_history=_esc(chat_history[:2000])))
        except Exception as e:
            log.warning("Groq analyze error -> fallback: %s", e)
            it = self._classify_intent(message)
            comps = {"intent": it["intent"], "product_match": 60, "urgency": 50,
                     "sentiment": 55, "chat_history": 50, "decision_maker": 70,
                     "intent_label": it["label"], "product": "Umum",
                     "urgency_label": "Sedang", "sentiment_label": "Netral",
                     "customer_stage": "Awareness"}
        w = {"intent": .30, "product_match": .20, "urgency": .20, "sentiment": .10,
             "chat_history": .10, "decision_maker": .10}
        score = round(sum(comps.get(k, 50) * w[k] for k in w))
        cat = "Hot Lead" if score >= 70 else ("Warm Lead" if score >= 40 else "Cold Lead")
        badge = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")
        return {"lead_score": score, "category": cat, "badge": badge,
                "components": {k: comps.get(k, 50) for k in w},
                "intent_label": comps.get("intent_label", ""),
                "product": comps.get("product", ""),
                "urgency_label": comps.get("urgency_label", ""),
                "sentiment_label": comps.get("sentiment_label", ""),
                "customer_stage": comps.get("customer_stage", ""),
                "analysis_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}

    def generate_reply(self, message: str, context: dict, kb: str = "") -> dict:
        try:
            hist = context.get("chat_history") or ""
            if isinstance(hist, list):
                hist = "\n".join(str(x) for x in hist[-12:])
            prompt = REPLY_PROMPT.format(
                customer_name=_esc(context.get("customer_name", "Customer")),
                message=_esc(message[:2000]),
                chat_history=_esc(hist[:2500] or "(belum ada riwayat)"),
                product=_esc(context.get("product", "Umum")),
                stage=_esc(context.get("customer_stage", "Awareness")),
                score=context.get("lead_score", 50),
                knowledge_chunks=_esc(kb[:3000] or "(tidak ada konteks)")
            )
            out = self._chat_json("Anda adalah AI Sales Assistant profesional. Output in JSON format.", prompt)
            if not isinstance(out, dict):
                raise ValueError(f"Groq returned non-dict: {type(out)}")
            if "suggested_reply" not in out:
                raise KeyError("suggested_reply missing from Groq response")
            return {"suggested_reply": out["suggested_reply"],
                    "confidence_score": min(99, _to_int(out.get("confidence_score", 70))),
                    "sources": out.get("sources", []), "fallback": out.get("fallback", "")}
        except Exception as e:
            log.warning("Groq reply error -> fallback: %s | type: %s", e, type(e).__name__)
            it = self._classify_intent(message)
            reply = "Halo Kak 😊\n\nTerima kasih sudah menghubungi ICC.\n\nUntuk memberi informasi yang tepat, boleh Kak beri tahu:"
            if any(w in message.lower() for w in ["harga", "biaya"]):
                reply += "  jumlah peserta, kebutuhan sertifikasi, dan lokasi perusahaan?"
            elif any(w in message.lower() for w in ["jadwal", "kapan"]):
                reply += "  lokasi / preferensi wilayah?"
            else:
                reply += "  produk apa yang Kakak butuhkan?"
            return {"suggested_reply": reply, "confidence_score": min(99, _to_int(it["intent"], 50) + 10),
                    "sources": [{"type": "faq", "reference": f"FAQ - {context.get('product', 'Umum')}"}],
                    "fallback": "Maaf kak, saya kurang yakin. Sales kami akan menghubungi segera."}


def groq_for(user: dict) -> GroqClient:
    return GroqClient(api_key=(user or {}).get("groq_api_key") or config.GROQ_API_KEY)
