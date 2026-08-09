#!/usr/bin/env python3
"""
Sales AI Assistant — FastAPI Backend v0.3
Gateway WA : Fonnte (api.fonnte.com)
LLM       : Groq (llama-3.3-70b-versatile, JSON mode) + fallback rule-based
DB        : Supabase Postgres (customers, chats, products, leads, upload)
Storage   : Supabase Storage (product uploads)
Endpoints : /health, /ws, /webhook/fonnte (+ /webhook/fonte alias),
            /api/v1/messages/send, /api/v1/assessment/analyze,
            /api/v1/reply/generate, /api/v1/customers,
            /api/v1/products/*, /api/v1/upload
"""
import os, json, hmac, hashlib, uuid, datetime, logging, io
import httpx

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()  # baca .env
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("sai")

app = FastAPI(title="Sales AI Assistant API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------- CONFIG ----------
FONNTE_TOKEN      = os.getenv("FONNTE_TOKEN", "")
FONNTE_FROM       = os.getenv("FONNTE_FROM_NUMBER", "6289876543210")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL        = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Frontend (index.html) dilayani di "/" — diakses via https://amcicccrm.my.id/salesai/
FRONTEND_FILE = os.getenv("FRONTEND_FILE", "/home/adminicc/workspace/sales-ai-assistant/index.html")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
HAS_SUPABASE = bool(SUPABASE_URL and (SUPABASE_KEY or SUPABASE_SERVICE_KEY))

# ---------- SUPABASE CLIENT ----------
try:
    from supabase import create_client
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY or SUPABASE_KEY)
    log.warning("[Supabase] Connected to %s", SUPABASE_URL)
except Exception as e:
    supabase_admin = None
    log.warning("[Supabase] Not available: %s", e)

# ---------- MOCK DATA (fallback in-memory) ----------
CUSTOMERS = {}
LEAD_SCORES = {}
AI_LOGS = []

# ---------- GROQ CLIENT ----------
try:
    from groq import Groq
except Exception:
    Groq = None

class GroqClient:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY) if (GROQ_API_KEY and Groq) else None
        self.available = self.client is not None

    def _chat_json(self, system: str, user: str, timeout: int = 30) -> dict:
        log.warning("[_chat_json] ENTRY - available=%s", self.available)
        if not self.available:
            raise RuntimeError("groq not configured")
        log.warning("[_chat_json] calling Groq API...")
        try:
            resp = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role":"system","content":system + " Output in JSON format."},{"role":"user","content":user}],
                temperature=0.3, max_tokens=800, top_p=0.9,
                response_format={"type":"json_object"},
                timeout=timeout,
            )
            log.warning("[_chat_json] Groq API returned")
            content = resp.choices[0].message.content
            log.warning("[Groq raw] %s", content[:500])
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                log.warning("Groq JSON decode error: %s | content: %s", e, content[:500])
                raise
        except Exception as e:
            log.warning("Groq API call failed: %s | type: %s", e, type(e).__name__)
            raise

    # ---- fallback rule-based (jika Groq gagal / tidak ada key) ----
    @staticmethod
    def _classify_intent(text: str) -> dict:
        t = text.lower()
        if any(w in t for w in ["harga","biaya","berapa","modal","tarif"]):
            return {"intent":80,"label":"Minta informasi"}
        if any(w in t for w in ["jadwal","kapan","waktu","tanggal"]):
            return {"intent":70,"label":"Tanya jadwal"}
        if any(w in t for w in ["sertifikat","skema","bnsp","asesor"]):
            return {"intent":75,"label":"Tanya sertifikasi"}
        if any(w in t for w in ["promo","diskon","daftar","registrasi","penawaran"]):
            return {"intent":85,"label":"Mau promo/daftar"}
        return {"intent":50,"label":"General question"}

    def analyze(self, message: str, chat_history: str = "") -> dict:
        """Lead scoring 6 komponen via Groq; fallback rule-based."""
        try:
            def _esc2(s):
                if not s: return ""
                s = str(s)
                return s.replace("{", "{{").replace("}", "}}")
            comps = self._chat_json("Anda adalah AI Sales Assistant profesional. Output in JSON format.",
                                    ASSESSMENT_PROMPT.format(
                                        message=_esc2(message[:2000]),
                                        chat_history=_esc2(chat_history[:2000])))
        except Exception as e:
            log.warning("Groq analyze error -> fallback: %s", e)
            it = self._classify_intent(message)
            comps = {"intent":it["intent"],"product_match":60,"urgency":50,
                     "sentiment":55,"chat_history":50,"decision_maker":70,
                     "intent_label":it["label"],"product":"Umum",
                     "urgency_label":"Sedang","sentiment_label":"Netral",
                     "customer_stage":"Awareness"}
        w = {"intent":.30,"product_match":.20,"urgency":.20,"sentiment":.10,
             "chat_history":.10,"decision_maker":.10}
        score = round(sum(comps.get(k,50)*w[k] for k in w))
        cat  = "Hot Lead" if score>=70 else ("Warm Lead" if score>=40 else "Cold Lead")
        badge= "🟢" if score>=70 else ("🟡" if score>=40 else "🔴")
        return {"lead_score":score,"category":cat,"badge":badge,
                "components":{k:comps.get(k,50) for k in w},
                "intent_label":comps.get("intent_label",""),
                "product":comps.get("product",""),
                "urgency_label":comps.get("urgency_label",""),
                "sentiment_label":comps.get("sentiment_label",""),
                "customer_stage":comps.get("customer_stage",""),
                "analysis_timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat()}

    def generate_reply(self, message: str, context: dict, kb: str = "") -> dict:
        """Suggested reply via Groq + knowledge context; fallback template."""
        try:
            # Escape braces in dynamic inputs so .format() doesnt choke on JSON in messages
            def _esc(s):
                if not s: return ""
                s = str(s)
                return s.replace("{", "{{").replace("}", "}}")

            hist = context.get("chat_history") or ""
            if isinstance(hist, list):
                hist = "\\n".join(str(x) for x in hist[-12:])
            prompt = REPLY_PROMPT.format(
                customer_name=_esc(context.get("customer_name","Customer")),
                message=_esc(message[:2000]),
                chat_history=_esc(hist[:2500] or "(belum ada riwayat)"),
                product=_esc(context.get("product","Umum")),
                stage=_esc(context.get("customer_stage","Awareness")),
                score=context.get("lead_score",50),
                knowledge_chunks=_esc(kb[:3000] or "(tidak ada konteks)")
            )
            out = self._chat_json("Anda adalah AI Sales Assistant profesional. Output in JSON format.", prompt)
            log.warning("[generate_reply] Groq response type: %s, keys: %s", type(out).__name__, list(out.keys()) if isinstance(out, dict) else 'not dict')
            # Handle case where Groq returns different structure
            if not isinstance(out, dict):
                raise ValueError(f"Groq returned non-dict: {type(out)}")
            if "suggested_reply" not in out:
                log.warning("[generate_reply] missing suggested_reply, full response: %s", str(out)[:500])
                raise KeyError("suggested_reply missing from Groq response")
            return {"suggested_reply":out["suggested_reply"],"confidence_score":min(99,int(out.get("confidence_score",70))),
                    "sources":out.get("sources",[]),"fallback":out.get("fallback","")}
        except Exception as e:
            log.warning("Groq reply error -> fallback: %s | type: %s", e, type(e).__name__)
            it = self._classify_intent(message)
            reply = "Halo Kak 😊\n\nTerima kasih sudah menghubungi ICC.\n\nUntuk memberi informasi yang tepat, boleh Kak beri tahu:"
            if any(w in message.lower() for w in ["harga","biaya"]):
                reply += "  jumlah peserta, kebutuhan sertifikasi, dan lokasi perusahaan?"
            elif any(w in message.lower() for w in ["jadwal","kapan"]):
                reply += "  lokasi / preferensi wilayah?"
            else:
                reply += "  produk apa yang Kakak butuhkan?"
            return {"suggested_reply":reply,"confidence_score":min(99,it["intent"]+10),
                    "sources":[{"type":"faq","reference":f"FAQ - {context.get('product','Umum')}"}],
                    "fallback":"Maaf kak, saya kurang yakin. Sales kami akan menghubungi segera."}

groq = GroqClient()

# ---------- PROMPTS ----------
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

# ---------- WebSocket ----------
class ConnectionManager:
    def __init__(self): self.connections = []
    async def connect(self, ws): await ws.accept(); self.connections.append(ws)
    def disconnect(self, ws):
        if ws in self.connections: self.connections.remove(ws)
    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try: await ws.send_json(data)
            except Exception: dead.append(ws)
        for ws in dead: self.disconnect(ws)

manager = ConnectionManager()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)

# ---------- FONNTE ----------
async def fonnte_send(target: str, text: str) -> dict:
    """Kirim pesan WA via Fonnte API."""
    if not FONNTE_TOKEN:
        return {"status_code":0,"error":"FONNTE_TOKEN not set"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://api.fonnte.com/send",
            data={"target":target,"message":text,"countryCode":"62"},
            headers={"Authorization":FONNTE_TOKEN})
        return {"status_code":r.status_code,"response":r.text}

# ---------- SUPABASE HELPERS ----------
def sb():
    return supabase_admin

def save_customer_db(phone: str, name: str, analysis: dict) -> dict:
    """Save customer to Supabase (upsert)."""
    if not HAS_SUPABASE:
        return {"status":"mock","phone":phone}
    try:
        data = {
            "phone": phone,
            "name": name,
            "last_score": analysis.get("lead_score", 0),
            "category": analysis.get("category", "Cold Lead"),
            "badge": analysis.get("badge", "🔴"),
            "last_message": analysis.get("intent_label", ""),
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        result = sb().table("customers").upsert(data, on_conflict="phone").execute()
        log.warning("[DB] Customer saved: %s", phone)
        return {"status":"saved","data":result.data}
    except Exception as e:
        log.warning("[DB] Customer save error: %s", e)
        return {"status":"error","error":str(e)}

def save_chat_db(phone: str, text: str, direction: str, analysis: dict = None) -> dict:
    """Save chat message to Supabase."""
    if not HAS_SUPABASE:
        return {"status":"mock","phone":phone}
    try:
        data = {
            "phone": phone,
            "text": text,
            "direction": direction,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "lead_score": analysis.get("lead_score", 0) if analysis else None,
            "category": analysis.get("category", "") if analysis else "",
            "intent_label": analysis.get("intent_label", "") if analysis else ""
        }
        result = sb().table("chats").insert(data).execute()
        log.warning("[DB] Chat saved: %s (%s)", phone, direction)
        return {"status":"saved","data":result.data}
    except Exception as e:
        log.warning("[DB] Chat save error: %s", e)
        return {"status":"error","error":str(e)}

async def upload_to_supabase(file: UploadFile) -> dict:
    """Upload file produk (PDF, gambar, dokumen K3/BNSP) ke Supabase Storage."""
    if not HAS_SUPABASE:
        # Mock mode — still need to consume the file to avoid errors
        content = await file.read()
        log.warning("[Upload] Mock mode — filename: %s, size: %d bytes", file.filename, len(content))
        return {"status":"mock","filename":file.filename, "size": len(content)}
    try:
        content = await file.read()
        ext = os.path.splitext(file.filename or "")[1]
        fname = f"{uuid.uuid4().hex}{ext}"
        bucket = "products"
        res = sb().storage.from_(bucket).upload(fname, content)
        if res.status_code == 200:
            public_url = sb().storage.from_(bucket).get_public_url(fname)
            log.warning("[Upload] %s -> %s", file.filename, public_url)
            return {"status":"uploaded","filename":fname,"public_url":public_url}
        else:
            return {"status":"error","code":res.status_code,"response":getattr(res, 'text', str(res))}
    except Exception as e:
        log.warning("[Upload] Error: %s", e)
        return {"status":"error","error":str(e)}

# ---------- CUSTOMER MANAGEMENT ----------
def build_customer(phone: str, name: str = None, analysis: dict = None) -> dict:
    """Get or create customer record."""
    if phone not in CUSTOMERS:
        CUSTOMERS[phone] = {
            "name": name or phone,
            "msgs": [],
            "unread": 0,
            "last": "",
            "score": analysis.get("lead_score", 0) if analysis else 0,
            "category": analysis.get("category", "Cold Lead") if analysis else "Cold Lead",
            "badge": analysis.get("badge", "🔴") if analysis else "🔴",
            "created": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    else:
        if name and CUSTOMERS[phone]["name"] == phone:
            CUSTOMERS[phone]["name"] = name
        if analysis:
            CUSTOMERS[phone]["score"] = analysis["lead_score"]
            CUSTOMERS[phone]["category"] = analysis["category"]
            CUSTOMERS[phone]["badge"] = analysis["badge"]
    # Also save to Supabase
    if analysis:
        save_customer_db(phone, CUSTOMERS[phone]["name"], analysis)
    return {"phone": phone, **CUSTOMERS[phone]}

def process_incoming(payload: dict):
    """Parse payload Fonnte (format webhook reply message) -> broadcast. Return analysis."""
    # format webhook reply message: {sender, message, name, pushname, device, ...}
    sender = payload.get("sender") or payload.get("pengirim") or payload.get("from")
    text   = payload.get("message") or payload.get("pesan") or payload.get("text")
    name   = payload.get("name") or payload.get("pushname") or sender
    if not sender or not text:
        return None, None, None

    cust  = build_customer(sender, name)
    analysis = groq.analyze(text)
    LEAD_SCORES[sender] = analysis

    # Save to in-memory
    cust["msgs"].append({"dir":"in","t":datetime.datetime.now().strftime("%H:%M"),"d":text})
    cust["unread"] += 1
    cust["last"] = text[:60]
    cust["score"] = analysis["lead_score"]
    cust["category"] = analysis["category"]
    cust["badge"] = analysis["badge"]

    # Save to Supabase
    save_customer_db(sender, name, analysis)
    save_chat_db(sender, text, "in", analysis)

    log.info("[incoming] %s (%s) -> %s (score=%s)", sender, name, text[:60], analysis["lead_score"])
    return cust, {"from":sender,"text":text,"timestamp":payload.get("timestamp") or payload.get("date")}, analysis

# ---------- KNOWLEDGE BASE ----------
PRODUCT_CATEGORIES = ["BNSP", "Kemnaker RI", "Reguler", "Umum"]
KB_CHUNK_SIZE = 500
KB_CHUNK_OVERLAP = 80
KB_STORE = []  # in-memory fallback when Supabase off

def chunk_text(text: str, size: int = KB_CHUNK_SIZE, overlap: int = KB_CHUNK_OVERLAP) -> list:
    """Simple paragraph-aware chunking. No vector DB."""
    text = (text or "").strip()
    if not text:
        return []
    # Split by blank lines first, then hard-cut long paragraphs
    parts, buf = [], []
    for para in text.replace("\r\n", "\n").split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            parts.append(para)
        else:
            start = 0
            while start < len(para):
                end = min(start + size, len(para))
                parts.append(para[start:end].strip())
                if end >= len(para):
                    break
                start = max(end - overlap, start + 1)
    # Merge tiny tails into previous when possible
    out = []
    for p in parts:
        if out and len(out[-1]) + 1 + len(p) <= size:
            out[-1] = out[-1] + "\n" + p
        else:
            out.append(p)
    return [{"idx": i, "text": c, "chars": len(c)} for i, c in enumerate(out) if c]

def _tokens(q: str) -> set:
    stop = {"yang","dan","atau","untuk","dari","dengan","pada","ini","itu","ada","saya","kami","kak","apakah","berapa","mohon","info","tentang","the","a","an","of","to","in"}
    return {w for w in "".join(ch.lower() if ch.isalnum() else " " for ch in (q or "")).split() if len(w) >= 3 and w not in stop}

def score_chunk(query: str, chunk: str, doc_name: str = "", category: str = "") -> float:
    """Keyword score: token hits + phrase bonus + category/name boost."""
    toks = _tokens(query)
    if not toks:
        return 0.0
    blob = f"{doc_name} {category} {chunk}".lower()
    hits = sum(1 for t in toks if t in blob)
    score = hits / max(len(toks), 1)
    # bigram phrase bonus
    words = [w for w in "".join(ch.lower() if ch.isalnum() else " " for ch in query).split() if len(w) >= 3]
    for i in range(len(words) - 1):
        phrase = f"{words[i]} {words[i+1]}"
        if phrase in blob:
            score += 0.25
    if category and category.lower() in (query or "").lower():
        score += 0.15
    return round(score, 4)

def search_kb_chunks(query: str, category: str = None, limit: int = 5) -> list:
    """Retrieve top chunks by keyword score from Supabase or in-memory."""
    rows = []
    if HAS_SUPABASE and sb():
        try:
            q = sb().from_("knowledge_base").select("id,name,category,chunks,kb_text,file_url,uploaded_at")
            if category and category in PRODUCT_CATEGORIES:
                q = q.eq("category", category)
            result = q.order("uploaded_at", desc=True).limit(50).execute()
            rows = result.data or []
        except Exception as e:
            log.warning("[KB search] Supabase error: %s", e)
            rows = []
    if not rows:
        rows = [r for r in KB_STORE if (not category or r.get("category") == category)]

    scored = []
    for row in rows:
        chunks = row.get("chunks") or []
        if isinstance(chunks, str):
            try:
                chunks = json.loads(chunks)
            except Exception:
                chunks = []
        if not chunks and row.get("kb_text"):
            chunks = chunk_text(row["kb_text"])
        for ch in chunks:
            text = ch.get("text") if isinstance(ch, dict) else str(ch)
            if not text:
                continue
            s = score_chunk(query, text, row.get("name",""), row.get("category",""))
            if s <= 0:
                continue
            scored.append({
                "score": s,
                "text": text[:1200],
                "name": row.get("name",""),
                "category": row.get("category",""),
                "doc_id": row.get("id"),
                "chunk_idx": ch.get("idx") if isinstance(ch, dict) else None,
                "file_url": row.get("file_url",""),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    # de-dupe near-identical tops
    out, seen = [], set()
    for item in scored:
        key = item["text"][:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out

def format_kb_context(chunks: list) -> str:
    if not chunks:
        return ""
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] ({c.get('category','?')} | {c.get('name','?')} | score={c.get('score',0)})\n{c.get('text','')}")
    return "\n\n".join(parts)

@app.post("/api/v1/products")
async def create_product(p: dict):
    """Buat/update produk pelatihan. {name, category, description, price_range, duration, kb_text}"""
    if not HAS_SUPABASE:
        return {"status":"mock","product_id":str(uuid.uuid4())}
    try:
        pid = p.get("id") or str(uuid.uuid4())
        data = {
            "id": pid,
            "name": p["name"],
            "category": p.get("category","Umum"),
            "description": p.get("description",""),
            "price_range": p.get("price_range",""),
            "duration": p.get("duration",""),
            "kb_text": p.get("kb_text",""),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        result = sb().table("products").upsert(data, on_conflict="id").execute()
        log.warning("[Product] Created: %s (%s)", p["name"], data["category"])
        return {"status":"saved","product_id":pid,"data":result.data}
    except Exception as e:
        log.warning("[Product] Error: %s", e)
        return {"status":"error","error":str(e)}

@app.get("/api/v1/products")
async def list_products(category: str = None):
    """List semua produk, optional filter category (BNSP/Kemnaker/Umum/Reguler)."""
    if not HAS_SUPABASE:
        return []
    try:
        q = sb().table("products").select("*")
        if category:
            q = q.eq("category", category)
        result = q.execute()
        return result.data or []
    except Exception as e:
        log.warning("[Products] Error: %s", e)
        return {"status":"error","error":str(e)}

@app.get("/api/v1/products/{pid}")
async def get_product(pid: str):
    """Get detail produk by ID, termasuk KB text untuk Suggested Reply."""
    if not HAS_SUPABASE:
        return {"status":"mock","id":pid}
    try:
        result = sb().from_("products").select("*").eq("id", pid).single().execute()
        return result.data
    except Exception as e:
        log.warning("[Product] Error: %s", e)
        return {"status":"error","error":str(e)}

@app.post("/api/v1/upload")
async def upload_product_file(file: UploadFile = File(...)):
    """Upload file produk (PDF, gambar, dokumen K3/BNSP) ke Supabase Storage."""
    result = await upload_to_supabase(file)
    return result

@app.post("/api/v1/knowledge/upload")
async def upload_knowledge(file: UploadFile = File(...), category: str = "Umum", name: str = "", extract_text: bool = True):
    """Upload file KB (PDF/txt) -> extract text -> simpan ke tabel knowledge_base.
    category: BNSP | Kemnaker | Reguler | Umum
    """
    if category not in PRODUCT_CATEGORIES:
        category = "Umum"

    # Read file content ONCE at the beginning
    content_bytes = await file.read()
    ext = os.path.splitext(file.filename or "")[1].lower()

    kb_text = ""
    if extract_text:
        ext_lower = ext
        try:
            if ext_lower == ".txt" or ext_lower in [".md"]:
                kb_text = content_bytes.decode("utf-8", errors="replace")
            elif ext_lower == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(content_bytes))
                    kb_text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
                except ImportError:
                    import fitz  # PyMuPDF
                    doc = fitz.open(stream=content_bytes, filetype="pdf")
                    kb_text = "\n\n".join(page.get_text() for page in doc)
                    doc.close()
            elif ext_lower == ".docx":
                from docx import Document
                doc = Document(io.BytesIO(content_bytes))
                kb_text = "\n\n".join(p.text or "" for p in doc.paragraphs if p.text.strip())
            elif ext_lower in [".xlsx", ".xls"]:
                from openpyxl import load_workbook
                wb = load_workbook(io.BytesIO(content_bytes), read_only=True, data_only=True)
                rows = []
                for ws in wb.worksheets:
                    for row in ws.iter_rows(values_only=True):
                        cells = [str(c) for c in row if c is not None]
                        if cells:
                            rows.append("\t".join(cells))
                kb_text = "\n".join(rows)
                wb.close()
            elif ext_lower in [".pptx"]:
                from pptx import Presentation
                prs = Presentation(io.BytesIO(content_bytes))
                kb_text = "\n\n".join(shape.text or "" for slide in prs.slides for shape in slide.shapes if hasattr(shape,"text"))
        except ImportError as ie:
            log.warning("[KB Upload] Missing dep for %s: %s", ext, ie)
        except Exception as e:
            log.warning("[KB Upload] %s extraction error: %s", ext, e)
            kb_text = f"(extraction error: {e})"

    if not kb_text:
        kb_text = f"File KB: {file.filename}. Buka dokumen untuk detail."

    # Upload file ke storage (re-create UploadFile untuk reuse)
    from fastapi import UploadFile as _UF
    reuse_file = _UF(filename=file.filename, file=io.BytesIO(content_bytes), headers={})
    upload_result = await upload_to_supabase(reuse_file)

    chunks = chunk_text(kb_text)
    doc_id = str(uuid.uuid4())
    record = {
        "id": doc_id,
        "category": category,
        "name": name or file.filename or "",
        "filename": file.filename or "",
        "file_url": upload_result.get("public_url", ""),
        "kb_text": kb_text[:50000],
        "chunks": chunks,
        "chunk_count": len(chunks),
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    if HAS_SUPABASE:
        try:
            result = sb().table("knowledge_base").insert(record).execute()
            log.warning("[KB Upload] %s -> category=%s, text_len=%d, chunks=%d", file.filename, category, len(kb_text), len(chunks))
            return {"status":"saved","data":result.data, "kb_text_length": len(kb_text), "chunk_count": len(chunks), "chunks_preview": chunks[:3]}
        except Exception as e:
            # fallback: store without chunks column if schema missing
            try:
                bare = {k:v for k,v in record.items() if k not in ("chunks","chunk_count")}
                result = sb().table("knowledge_base").insert(bare).execute()
                log.warning("[KB Upload] saved without chunks col: %s", e)
                KB_STORE.append(record)
                return {"status":"saved_partial","data":result.data, "kb_text_length": len(kb_text), "chunk_count": len(chunks), "note":"chunks stored in-memory only; add JSONB column chunks", "error": str(e)}
            except Exception as e2:
                log.warning("[KB Upload] DB error: %s", e2)
                KB_STORE.append(record)
                return {"status":"saved_memory","file":upload_result, "kb_text_length": len(kb_text), "chunk_count": len(chunks), "error": str(e2)}
    else:
        KB_STORE.append(record)
        log.warning("[KB Upload] Memory mode — category=%s, name=%s, text_len=%d, chunks=%d", category, name or file.filename, len(kb_text), len(chunks))
        return {"status":"mock_saved","category":category,"name":name or file.filename,"kb_text_length":len(kb_text),"chunk_count":len(chunks),"chunks_preview":chunks[:3],"file":upload_result}

@app.get("/api/v1/knowledge/search")
async def knowledge_search(q: str = "", cat: str = None, limit: int = 5):
    """Keyword search over KB chunks (Option A: no vector)."""
    if not q.strip():
        return {"status":"error","error":"q wajib"}
    category = None
    if cat and cat.strip() and cat.strip() in PRODUCT_CATEGORIES:
        category = cat.strip()
    hits = search_kb_chunks(q, category=category, limit=max(1, min(limit, 20)))
    return {"status":"success","query":q,"category":category,"count":len(hits),"hits":hits}

@app.get("/api/v1/knowledge/{category}")
async def get_knowledge(category: str):
    """List KB docs for category (BNSP / Kemnaker RI / Reguler / Umum)."""
    if category not in PRODUCT_CATEGORIES:
        return {"status":"error","error":f"Invalid category. Valid: {PRODUCT_CATEGORIES}"}
    rows = []
    if HAS_SUPABASE and sb():
        try:
            result = sb().from_("knowledge_base").select("id,name,category,file_url,uploaded_at,chunk_count,kb_text,chunks").eq("category", category).order("uploaded_at", desc=True).execute()
            rows = result.data or []
        except Exception as e:
            log.warning("[Knowledge] Error: %s", e)
            rows = []  # fallback to in-memory
    if not rows:
        rows = [r for r in KB_STORE if r.get("category") == category]
    docs = []
    for p in rows:
        ch = p.get("chunks") or []
        if isinstance(ch, str):
            try: ch = json.loads(ch)
            except Exception: ch = []
        docs.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "category": p.get("category"),
            "url": p.get("file_url"),
            "uploaded_at": p.get("uploaded_at"),
            "chunk_count": p.get("chunk_count") or len(ch),
            "preview": (p.get("kb_text") or "")[:400],
        })
    return {"category":category,"docs":docs,"count":len(docs)}

# ---------- ROUTES ----------
@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Sajikan frontend app - https://amcicccrm.my.id/salesai/"""
    return FileResponse(FRONTEND_FILE)

@app.get("/health")
async def health():
    return {"status":"ok","groq_ready":groq.available,"groq_model":GROQ_MODEL,
            "fonnte_ready":bool(FONNTE_TOKEN),
            "supabase_ready":HAS_SUPABASE,
            "kb_docs_memory":len(KB_STORE),
            "kb_mode":"chunk+keyword"}

@app.post("/webhook/fonnte")
async def webhook_fonnte(req: Request):
    """Webhook Fonnte: device-status {device,stateid} ATAU pesan masuk {sender,message,name}."""
    payload = await req.json()
    if "stateid" in payload or ("device" in payload and "message" not in payload and "sender" not in payload):
        log.info("[webhook-device-status] %s", json.dumps(payload, ensure_ascii=False)[:300])
        return {"status":"received","type":"device_status"}
    log.info("[webhook-raw] %s", json.dumps(payload, ensure_ascii=False)[:500])
    cust, msg, analysis = process_incoming(payload)
    if cust is None:
        return {"status":"received","type":"skip"}
    await manager.broadcast({"type":"chat_incoming","customer":cust,"message":msg,"analysis":analysis})
    return {"status":"received","type":"message"}

@app.post("/webhook/fonte")
async def webhook_fonte(req: Request):
    """Alias PRD (Fonte) - parse payload Fonnte yang sama."""
    return await webhook_fonnte(req)

@app.post("/api/v1/assessment/analyze")
async def assess(req: Request):
    d = await req.json()
    analysis = groq.analyze(d.get("message",""), d.get("chat_history",""))
    AI_LOGS.append({"type":"assessment","input":d,"output":analysis,
                    "ts":datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return {"status":"success","data":analysis}

@app.post("/api/v1/reply/generate")
async def reply_generate(req: Request):
    d = await req.json()
    kb = d.get("knowledge_chunks","")
    product = d.get("context",{}).get("product","Umum")
    message = d.get("message","")
    hits = []

    # Auto-retrieve relevant chunks (Option A: keyword scoring)
    if not kb:
        cat_match = None
        for cat in PRODUCT_CATEGORIES:
            if cat.lower() in (product or "").lower() or cat.lower() in (message or "").lower():
                cat_match = cat
                break
        hits = search_kb_chunks(message or product, category=cat_match, limit=5)
        # if category filter too strict, broaden
        if not hits and cat_match:
            hits = search_kb_chunks(message or product, category=None, limit=5)
        kb = format_kb_context(hits)
        log.warning("[reply_generate] KB chunks: cat=%s hits=%d len=%d", cat_match, len(hits), len(kb))

    log.warning("[reply_generate] message: %s", message[:100])
    log.warning("[reply_generate] context: %s", d.get("context",{}))
    log.warning("[reply_generate] kb length: %d", len(kb))
    reply = groq.generate_reply(message, d.get("context",{}), kb)
    if isinstance(reply, dict) and "suggested_reply" in reply:
        reply["kb_hits"] = [{"name":h.get("name"),"category":h.get("category"),"score":h.get("score"),"chunk_idx":h.get("chunk_idx")} for h in hits]
        extra = [{"type":"kb","reference":f"{h.get('category','')}/{h.get('name','')}#{h.get('chunk_idx')}"} for h in hits[:3]]
        reply["sources"] = (reply.get("sources") or []) + extra
        reply["confidence"] = reply.get("confidence_score", 0)
    else:
        reply = {"suggested_reply":"(fallback error)",
                 "confidence_score": reply.get("confidence_score",20) if isinstance(reply,dict) else 20,
                 "sources":[],
                 "fallback": str(reply.get("fallback","Maaf kak, sale kami akan hubungi segeri")),
                 "kb_hits": []}
    AI_LOGS.append({"customer_id":d.get("customer_id"),"reply":reply,
                    "ts":datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return {"status":"success","data":reply}

@app.post("/api/v1/messages/send")
async def send_message(req: Request):
    """Kirim balasan WA via Fonnte. {to, text}"""
    d = await req.json()
    to, text = d.get("to",""), d.get("text","")
    if not to or not text:
        raise HTTPException(400, "to & text wajib")
    res = await fonnte_send(to, text)
    return {"status":"success","sent":res["status_code"]==200,"fonnte":res}

@app.get("/api/v1/customers")
async def list_customers():
    return [{"phone":p, **c} for p,c in CUSTOMERS.items()]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)