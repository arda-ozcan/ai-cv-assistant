// Backend URL – lokal geliştirmede:
const BACKEND_URL = "https://ai-cv-assistant-9niq.onrender.com";

// Her kullanıcı için benzersiz session id (localStorage’da saklıyoruz)
let sessionId = localStorage.getItem("ardaAssistantSessionId");
if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem("ardaAssistantSessionId", sessionId);
}

function getOrCreateSessionId() {
    let id = localStorage.getItem("arda_session_id");
    if (!id) {
        if (window.crypto && crypto.randomUUID) {
            id = crypto.randomUUID();
        } else {
            id = "sess-" + Date.now();
        }
        localStorage.setItem("arda_session_id", id);
    }
    return id;
}
const SESSION_ID = getOrCreateSessionId();

const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");
const quickButtons = document.querySelectorAll(".quick-btn");

let history = [];
let isSending = false;
let typingRow = null;


// Footer yılı
const yearSpan = document.getElementById("year");
if (yearSpan) {
    yearSpan.textContent = new Date().getFullYear();
}

// İlk karşılama mesajını ekle
window.addEventListener("DOMContentLoaded", () => {
    addMessage(
        "assistant",
        "Merhaba 👋\n\nBen Arda’nın profesyonel yapay zeka asistanıyım.\n" +
        "Onur Arda Özcan hakkında merak ettiğiniz her şeyi sorabilirsiniz.\n\n" +
        "Başlamak için sağ alttaki önerilen sorulardan birini de seçebilirsiniz."
    );
    autoResize();
    // Sayfa açılır açılmaz, kullanıcının izniyle konum iste
    requestUserLocation();

    // CV görünümüne dön butonu
const focusExitBtn = document.querySelector(".focus-exit-btn");
if (focusExitBtn) {
    focusExitBtn.addEventListener("click", () => {
        exitFocusMode();
    });
}

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        exitFocusMode();
    }
});

});

// Mesaj balonu ekleme
function addMessage(role, content, options = {}) {
    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = `bubble ${role}`;
    bubble.textContent = content;

    row.appendChild(bubble);
    messagesEl.appendChild(row);

    // Küçük animasyon
    requestAnimationFrame(() => {
        bubble.classList.add("appear");
    });

    scrollToBottom();

    if (!options.skipHistory) {
        history.push({ role: role === "user" ? "user" : "assistant", content });
    }

    // ↙︎ BURASI YENİ: her mesajdan sonra taşma var mı kontrol et
    maybeEnterFocusModeOnOverflow();

    return row;
}


// Typing indicator
function showTypingIndicator() {
    removeTypingIndicator();

    typingRow = document.createElement("div");
    typingRow.className = "message-row assistant";

    const bubble = document.createElement("div");
    bubble.className = "bubble assistant appear";

    const wrapper = document.createElement("div");
    wrapper.className = "typing-indicator";

    for (let i = 0; i < 3; i++) {
        const dot = document.createElement("div");
        dot.className = "dot";
        wrapper.appendChild(dot);
    }

    bubble.appendChild(wrapper);
    typingRow.appendChild(bubble);
    messagesEl.appendChild(typingRow);
    scrollToBottom();
}

function removeTypingIndicator() {
    if (typingRow && typingRow.parentNode) {
        typingRow.parentNode.removeChild(typingRow);
    }
    typingRow = null;
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Form submit
formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    await handleSend();
});

// Enter ile gönder (Shift+Enter yeni satır)
inputEl.addEventListener("keydown", async (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        await handleSend();
    }
});

quickButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
        const text = btn.getAttribute("data-text");
        inputEl.value = text;
        await handleSend();
    });
});

async function handleSend() {
    if (isSending) return;

    const text = inputEl.value.trim();
    if (!text) return;

    // Kullanıcı mesajını ekle
    addMessage("user", text);
    inputEl.value = "";
    autoResize();

    try {
        isSending = true;
        formEl.querySelector(".send-btn").disabled = true;
        showTypingIndicator();

        const payload = {
            message: text,
            history: history,
            session_id: sessionId,
            session_id: SESSION_ID   
        };

        const res = await fetch(BACKEND_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            console.error("Chat error:", errorData);
            removeTypingIndicator();
            addMessage(
                "assistant",
                "Şu anda yanıt verirken bir sorun yaşadım. " +
                "Lütfen birkaç saniye sonra tekrar dener misiniz?"
            );
            return;
        }

        const data = await res.json();
        removeTypingIndicator();

        if (data && data.reply) {
            addMessage("assistant", data.reply);
        } else {
            addMessage(
                "assistant",
                "Beklenmeyen bir yanıt aldım, ancak backend çalışıyor görünüyor. " +
                "Lütfen soruyu yeniden formüle etmeyi deneyin."
            );
        }
    } catch (err) {
        console.error(err);
        removeTypingIndicator();
        addMessage(
            "assistant",
            "Bağlantı kurulurken bir hata oluştu. " +
            "Backend sunucusunun çalıştığından emin olun (http://localhost:8000)."
        );
    } finally {
        isSending = false;
        formEl.querySelector(".send-btn").disabled = false;
    }
}

function requestUserLocation() {
    if (!("geolocation" in navigator)) {
        console.warn("Tarayıcı geolocation özelliğini desteklemiyor.");
        return;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const { latitude, longitude, accuracy } = position.coords;

            console.log("Konum alındı:", latitude, longitude, "±", accuracy, "m");

            fetch("http://localhost:8000/save-location", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    latitude,
                    longitude,
                    accuracy,
                    session_id: SESSION_ID
                })
            }).catch((err) => {
                console.error("Konum backend'e gönderilirken hata:", err);
            });
        },
        (error) => {
            console.warn("Konum alınamadı / kullanıcı izin vermedi:", error);
            // İstersen burada küçük bir bilgi mesajı gösterebilirsin
        },
        {
            enableHighAccuracy: true,
            timeout: 8000,
            maximumAge: 0
        }
    );
}


// Textarea otomatik yükseklik
function autoResize() {
    inputEl.style.height = "auto";
    inputEl.style.height = inputEl.scrollHeight + "px";
}

inputEl.addEventListener("input", autoResize);

// Lokasyon pill tooltip için tıklama ile aç/kapa (mobil uyumlu)
const locationPill = document.querySelector(".pill-location");

if (locationPill) {
    locationPill.addEventListener("click", (e) => {
        e.stopPropagation();
        locationPill.classList.toggle("tooltip-open");
    });

    // Dışarı tıklanınca kapat
    document.addEventListener("click", () => {
        locationPill.classList.remove("tooltip-open");
    });
}

function enterFocusMode() {
    if (!document.body.classList.contains("focus-chat")) {
        document.body.classList.add("focus-chat");
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}


function exitFocusMode() {
    document.body.classList.remove("focus-chat");
}

/**
 * Mesaj alanı kartın içine sığmıyorsa (scroll oluşmuşsa) focus moda geç.
 */
function maybeEnterFocusModeOnOverflow() {
    const cardEl = document.querySelector(".chat-panel .card");
    if (!cardEl) return;

    // 1) Kart ekran için fazla mı yüksek?
    const rect = cardEl.getBoundingClientRect();
    const cardTooTall = rect.bottom > window.innerHeight - 40;

    // 2) Sohbet belli bir uzunluğu geçti mi?
    const messageCount = history.length;  // user + assistant
    const longConversation = messageCount >= 6;

    if (cardTooTall || longConversation) {
        enterFocusMode();
    }
}



