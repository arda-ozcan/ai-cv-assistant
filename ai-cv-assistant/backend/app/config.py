from pydantic import BaseModel
import os
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()


class Settings(BaseModel):
    # FastAPI ayarları
    app_name: str = "Arda CV Assistant Backend"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # LLM sunucusu ayarları (OpenAI uyumlu API varsayıyoruz)
    # Örnek: http://localhost:11434/v1  (Ollama OpenAI uyumlu mod)
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:11434/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "no-key-required")  # bazı local serverlar key istemez
    llm_model: str = os.getenv("LLM_MODEL", "llama3")  # kullanmak istediğin model adı

    # Varsayılan LLM parametreleri
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "800"))

    # Data dosyalarının yolu
    data_dir: str = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


settings = Settings()
