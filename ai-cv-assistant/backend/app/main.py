from fastapi import FastAPI, HTTPException, Request
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from pathlib import Path
from fastapi.responses import HTMLResponse
from datetime import datetime
from io import StringIO
from pydantic import BaseModel
import json
import csv
from .config import settings
from .schemas import ChatRequest, ChatResponse, ChatMessage
from .llm_client import call_llm


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

# CORS - frontend farklı origin'den istek atacaksa gerekli
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # İstersen burada domainini kısıtlayabilirsin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_system_prompt() -> str:
    system_path = Path(settings.data_dir) / "system_prompt.md"
    if not system_path.exists():
        raise FileNotFoundError(f"system_prompt.md bulunamadı: {system_path}")
    return system_path.read_text(encoding="utf-8")

def load_profile() -> str:
    profile_path = Path(settings.data_dir) / "profile.md"
    if not profile_path.exists():
        return ""  # profil yoksa sessizce boş dön, hata verme
    return profile_path.read_text(encoding="utf-8")

def load_projects_text() -> str:
    """
    data/projects.json içindeki projeleri, modele okunabilir
    kısa bir metne çevirip döner.
    """
    projects_path = Path(settings.data_dir) / "projects.json"
    if not projects_path.exists():
        return ""

    try:
        data = json.loads(projects_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    if not isinstance(data, list):
        return ""

    lines: list[str] = []
    for i, proj in enumerate(data, start=1):
        name = proj.get("name", "İsimsiz Proje")
        role = proj.get("role", "")
        tech_stack = proj.get("tech_stack", [])
        description = proj.get("description", "")
        highlights = proj.get("highlights", [])
        github = proj.get("github")
        live_demo = proj.get("live_demo")

        lines.append(f"{i}. Proje: {name}")
        if role:
            lines.append(f"   Rolü: {role}")
        if tech_stack:
            lines.append(f"   Teknolojiler: {', '.join(tech_stack)}")
        if description:
            lines.append(f"   Açıklama: {description}")
        if highlights:
            lines.append("   Öne çıkan noktalar:")
            for h in highlights:
                lines.append(f"     - {h}")
        if github:
            lines.append(f"   GitHub: {github}")
        if live_demo:
            lines.append(f"   Canlı demo: {live_demo}")
        lines.append("")  # projeler arasına boş satır

    return "\n".join(lines)



def load_faq() -> str:
    faq_path = Path(settings.data_dir) / "faq.md"
    if not faq_path.exists():
        return ""
    return faq_path.read_text(encoding="utf-8")


# 🔥 BURASI YENİ: log yazan küçük yardımcı fonksiyon
from datetime import datetime
from pathlib import Path
import json

LOG_DIR = Path.home() / ".arda_cv_logs"
LOG_FILE = LOG_DIR / "chat_logs.jsonl"

# Konum log dosyası
LOCATION_FILE = LOG_DIR / "locations.jsonl"


class LocationPayload(BaseModel):
    latitude: float
    longitude: float
    accuracy: float | None = None
    session_id: str | None = None

def get_filtered_entries(
    selected_date: str | None,
    filter_ip: str | None,
    filter_session: str | None,
):
    """
    Log dosyasını okur, tarihe ve isteğe bağlı IP / session filtrelerine göre süzer.

    Ayrıca aynı session_id için LOCATION_FILE içindeki
    son konum kaydını bulur ve her entry'ye _location_str ekler.
    """
    # Tarih seçilmemişse: bugün
    if selected_date is None:
        selected_date = datetime.utcnow().date().isoformat()

    entries: list[dict] = []
    ips: set[str] = set()
    sessions: set[str] = set()

    # 1) Önce konum loglarını oku ve session_id -> son konum map'i oluştur
    location_by_session: dict[str, dict] = {}
    if LOCATION_FILE.exists():
        lines_loc = LOCATION_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines_loc:
            try:
                loc = json.loads(line)
            except json.JSONDecodeError:
                continue

            sess = loc.get("session_id") or "unknown"
            ts = loc.get("timestamp")
            if not ts:
                continue

            try:
                dt_loc = datetime.fromisoformat(ts)
            except Exception:
                continue

            # Aynı session_id için en yeni konumu tut
            old = location_by_session.get(sess)
            if old is None:
                location_by_session[sess] = {"dt": dt_loc, "data": loc}
            else:
                if dt_loc > old["dt"]:
                    location_by_session[sess] = {"dt": dt_loc, "data": loc}

    # 2) Sohbet loglarını oku
    if not LOG_FILE.exists():
        return entries, selected_date, ips, sessions

    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts = entry.get("timestamp")
        if not ts:
            continue

        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            # Bozuk timestamp varsa atla
            continue

        date_str = dt.date().isoformat()
        if date_str != selected_date:
            continue

        ip = entry.get("ip", "unknown")
        sess = entry.get("session_id", "unknown")

        ips.add(ip)
        sessions.add(sess)

        # IP filtresi
        if filter_ip and ip != filter_ip:
            continue

        # Session filtresi
        if filter_session and sess != filter_session:
            continue

        # Saat/dakika
        entry["_time_str"] = dt.strftime("%H:%M")

        # Konum string'i ekle
        loc_info = location_by_session.get(sess)
        if loc_info is not None:
            loc_data = loc_info["data"]
            lat = loc_data.get("latitude")
            lon = loc_data.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                # İstersen burayı daha az hassas yapabilirsin (2-3 decimal)
                entry["_location_str"] = f"📍 {lat:.5f}, {lon:.5f}"
            else:
                entry["_location_str"] = "📍"
        else:
            # Konum izni yok / alınmamış
            entry["_location_str"] = "❌"

        entries.append(entry)

    return entries, selected_date, ips, sessions


def append_chat_log(
    user_message: str,
    assistant_reply: str,
    session_id: str | None = None,
    ip: str | None = None,
) -> None:
    """
    Her sohbet adımını kullanıcının ev dizinindeki
    C:\\Users\\Arda\\.arda_cv_logs\\chat_logs.jsonl dosyasına yazar.
    """
    LOG_DIR.mkdir(exist_ok=True)

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id or "unknown",
        "ip": ip or "unknown",
        "user_message": user_message,
        "assistant_reply": assistant_reply,
    }

    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("Log yazma hatası:", e)



@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}





@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    try:
        system_prompt = load_system_prompt()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    profile_text = load_profile()
    faq_text = load_faq()
    projects_text = load_projects_text()  # 🔹 YENİ

    messages = []

    # Ana system prompt
    messages.append({"role": "system", "content": system_prompt})

    # Profil özeti
    if profile_text:
        messages.append({
            "role": "system",
            "content": (
                "Aşağıda Onur Arda Özcan'ın güncel profil özeti var. "
                "Buradaki bilgiler güncel kabul edilir:\n\n"
                + profile_text
            ),
        })

    # FAQ (lokasyon, maaş, kariyer vb.)
    if faq_text:
        messages.append({
            "role": "system",
            "content": (
                "Aşağıda Arda hakkında sık sorulan sorular ve net yanıtları var. "
                "Lokasyon, maaş beklentisi, kariyer hedefi gibi konularda "
                "buradaki cevapları esas al:\n\n"
                + faq_text
            ),
        })

    # 🔹 Projeler
    if projects_text:
        messages.append({
            "role": "system",
            "content": (
                "Aşağıda Arda'nın öne çıkan projeleri, rolleri ve kullandığı teknolojiler listelenmiştir. "
                "Projeleriyle ilgili sorularda bu listeden yararlan:\n\n"
                + projects_text
            ),
        })


    if request.history:
        for msg in request.history:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
            else:
                role = getattr(msg, "role", "user")
                content = getattr(msg, "content", "")
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": request.message})

    try:
        reply = await call_llm(messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM hatası: {e}")

    # 🔥 IP ve session_id’yi al
    client_ip = http_request.client.host if http_request.client else None
    session_id = request.session_id

    # 🔥 Log’a yaz
    append_chat_log(
        user_message=request.message,
        assistant_reply=reply,
        session_id=session_id,
        ip=client_ip,
    )

    return ChatResponse(reply=reply)

@app.post("/save-location")
async def save_location(payload: LocationPayload, request: Request):
    """
    Kullanıcı konuma izin verirse, tarayıcıdan gelen GPS verisini kaydeder.
    """
    client_ip = request.client.host if request.client else "unknown"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": payload.session_id or "unknown",
        "ip": client_ip,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "accuracy": payload.accuracy,
    }

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOCATION_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("Konum loglanırken hata:", e)

    return {"status": "ok"}



from fastapi.responses import HTMLResponse

@app.get("/admin/logs", response_class=HTMLResponse)
async def admin_logs(
    selected_date: str | None = None,
    filter_ip: str | None = None,
    filter_session: str | None = None,
):
    """
    Admin panel:
      - Tarih filtresi
      - IP filtresi
      - Session filtresi
      - Her satırda saat + konum
      - Hem kullanıcı hem asistan balonları
    """
    entries, selected_date, ips, sessions = get_filtered_entries(
        selected_date, filter_ip, filter_session
    )

    html_parts: list[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Arda CV Assistant – Log Viewer</title>",
        "<style>",
        "body{font-family:-apple-system,system-ui,sans-serif;background:#f3f4f6;margin:0;padding:24px;}",
        "h1{margin-bottom:6px;font-size:20px;}",
        ".subtitle{font-size:13px;color:#6b7280;margin-bottom:16px;}",
        ".filter-bar{margin-bottom:10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:13px;}",
        "label{font-size:13px;color:#374151;}",
        "input[type=date], select{padding:4px 8px;border-radius:6px;border:1px solid #d1d5db;font-size:13px;}",
        "button{padding:5px 10px;border-radius:6px;border:1px solid #9ca3af;background:#fff;cursor:pointer;font-size:13px;}",
        "button:hover{background:#e5e7eb;}",
        ".export-bar{margin-bottom:14px;display:flex;gap:8px;font-size:13px;}",
        ".export-link{padding:4px 9px;border-radius:6px;border:1px solid #9ca3af;background:#fff;text-decoration:none;color:#111827;}",
        ".export-link:hover{background:#e5e7eb;}",
        ".session{background:#fff;border-radius:12px;padding:12px 14px;margin-bottom:12px;border:1px solid #e5e7eb;}",
        ".session-header{font-size:13px;color:#4b5563;margin-bottom:6px;display:flex;justify-content:space-between;gap:8px;}",
        ".session-badge{font-size:11px;color:#6b7280;}",
        ".msg{margin:6px 0;padding:6px 8px;border-radius:8px;background:#f9fafb;}",
        ".msg-user{border-left:3px solid #2563eb;}",
        ".msg-assistant{border-left:3px solid #10b981;background:#ecfdf5;}",
        ".timestamp{font-size:10px;color:#9ca3af;margin-top:2px;}",
        ".bubble-label{font-size:11px;font-weight:600;margin-bottom:2px;}",
        ".bubble-text{font-size:13px;white-space:pre-wrap;}",
        ".empty{background:#fff;border-radius:12px;padding:14px 16px;border:1px solid #e5e7eb;font-size:14px;color:#6b7280;}",
        "</style></head><body>",
        "<h1>Arda CV Assistant – Sohbet Logları</h1>",
        f"<div class='subtitle'>Seçili tarih: <strong>{selected_date}</strong></div>",
        "<form method='get' class='filter-bar'>",
        "<label for='date'>Tarih:</label>",
        f"<input type='date' id='date' name='selected_date' value='{selected_date}'>",
        "<label for='ip'> IP:</label>",
        "<select id='ip' name='filter_ip'>",
        "<option value=''>Hepsi</option>",
    ]

    # IP seçenekleri
    for ip in sorted(ips):
        selected_attr = " selected" if filter_ip == ip else ""
        html_parts.append(f"<option value='{ip}'{selected_attr}>{ip}</option>")
    html_parts.append("</select>")

    # Session seçenekleri
    html_parts.append("<label for='session'> Session:</label>")
    html_parts.append("<select id='session' name='filter_session'>")
    html_parts.append("<option value=''>Hepsi</option>")
    for sess in sorted(sessions):
        selected_attr = " selected" if filter_session == sess else ""
        html_parts.append(f"<option value='{sess}'{selected_attr}>{sess}</option>")
    html_parts.append("</select>")

    html_parts.append("<button type='submit'>Filtrele</button>")
    html_parts.append("</form>")

    # Export linkleri
    export_base = f"/admin/logs/export?selected_date={selected_date}"
    if filter_ip:
        export_base += f"&filter_ip={filter_ip}"
    if filter_session:
        export_base += f"&filter_session={filter_session}"

    html_parts.append("<div class='export-bar'>")
    html_parts.append(
        f"<a class='export-link' href='{export_base}&format=csv'>CSV indir</a>"
    )
    html_parts.append(
        f"<a class='export-link' href='{export_base}&format=json'>JSON indir</a>"
    )
    html_parts.append("</div>")

    # Kayıt yoksa
    if not entries:
        html_parts.append(
            "<div class='empty'>Seçili tarih ve filtreler için herhangi bir sohbet kaydı bulunamadı.</div>"
        )
        html_parts.append("</body></html>")
        return HTMLResponse("".join(html_parts), status_code=200)

    # Session + IP'ye göre gruplama
    sessions_map: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        key = (e.get("session_id", "unknown"), e.get("ip", "unknown"))
        sessions_map.setdefault(key, []).append(e)

    # En yeni seanslar üstte
    for (session_id, ip), sess_entries in reversed(list(sessions_map.items())):
        # Seans içi mesajları zamana göre sırala
        sess_entries.sort(key=lambda e: e.get("timestamp", ""))

        html_parts.append("<div class='session'>")
        html_parts.append(
            f"<div class='session-header'>"
            f"<div>Session: <strong>{session_id}</strong></div>"
            f"<div class='session-badge'>IP: {ip}</div>"
            f"</div>"
        )

        # Her entry: kullanıcı + asistan balonu
        for e in sess_entries:
            ts_raw = e.get("timestamp", "")
            time_str = e.get("_time_str", "")
            loc_str = e.get("_location_str", "❌")

            user_msg = e.get("user_message", "")
            assistant_msg = e.get("assistant_reply", "")

            # Kullanıcı
            html_parts.append("<div class='msg msg-user'>")
            html_parts.append("<div class='bubble-label'>Kullanıcı</div>")
            html_parts.append(f"<div class='bubble-text'>{user_msg}</div>")
            if time_str:
                html_parts.append(f"<div class='timestamp'>{time_str} · {loc_str}</div>")
            elif ts_raw:
                html_parts.append(f"<div class='timestamp'>{ts_raw} · {loc_str}</div>")
            else:
                html_parts.append(f"<div class='timestamp'>{loc_str}</div>")
            html_parts.append("</div>")

            # Asistan (varsa)
            if assistant_msg:
                html_parts.append("<div class='msg msg-assistant'>")
                html_parts.append("<div class='bubble-label'>Asistan</div>")
                html_parts.append(f"<div class='bubble-text'>{assistant_msg}</div>")
                if time_str:
                    html_parts.append(f"<div class='timestamp'>{time_str} · {loc_str}</div>")
                elif ts_raw:
                    html_parts.append(f"<div class='timestamp'>{ts_raw} · {loc_str}</div>")
                else:
                    html_parts.append(f"<div class='timestamp'>{loc_str}</div>")
                html_parts.append("</div>")

        html_parts.append("</div>")  # .session

    html_parts.append("</body></html>")
    return HTMLResponse("".join(html_parts), status_code=200)


@app.get("/admin/logs/export")
async def export_logs(
    format: str = "csv",
    selected_date: str | None = None,
    filter_ip: str | None = None,
    filter_session: str | None = None,
):
    """
    Seçili tarih + filtrelere göre logları CSV veya JSON olarak indir.
    """
    entries, selected_date, _, _ = get_filtered_entries(
        selected_date, filter_ip, filter_session
    )

    # Geçici alanları (_time_str) dışarı at
    clean_entries = []
    for e in entries:
        clean_entries.append(
            {k: v for k, v in e.items() if not k.startswith("_")}
        )

    if format.lower() == "json":
        filename = f"arda-logs-{selected_date}.json"
        return JSONResponse(
            content=clean_entries,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Varsayılan: CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "session_id", "ip", "user_message", "assistant_reply"])
    for e in clean_entries:
        writer.writerow(
            [
                e.get("timestamp", ""),
                e.get("session_id", ""),
                e.get("ip", ""),
                e.get("user_message", ""),
                e.get("assistant_reply", ""),
            ]
        )

    filename = f"arda-logs-{selected_date}.csv"
    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
