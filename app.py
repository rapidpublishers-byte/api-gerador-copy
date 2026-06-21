import base64
import glob
import io
import os
import re
import tempfile
import time
import wave
from pathlib import Path

from flask import Flask, after_this_request, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from google import genai
from google.genai import types
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
APP_HTML = BASE_DIR / "gerador.html"

app = Flask(__name__, static_folder=None)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash").strip()
GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview").strip()

ALLOWED_UPLOAD_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".mp4", ".mov", ".webm", ".mkv", ".avi"
}

VOICE_OPTIONS = [
    {"name": "Zephyr", "label": "Zephyr — Bright"},
    {"name": "Puck", "label": "Puck — Upbeat"},
    {"name": "Charon", "label": "Charon — Informative"},
    {"name": "Kore", "label": "Kore — Firm"},
    {"name": "Fenrir", "label": "Fenrir — Excitable"},
    {"name": "Leda", "label": "Leda — Youthful"},
    {"name": "Orus", "label": "Orus — Firm"},
    {"name": "Aoede", "label": "Aoede — Breezy"},
    {"name": "Callirrhoe", "label": "Callirrhoe — Easy-going"},
    {"name": "Autonoe", "label": "Autonoe — Bright"},
    {"name": "Enceladus", "label": "Enceladus — Breathy"},
    {"name": "Iapetus", "label": "Iapetus — Clear"},
    {"name": "Umbriel", "label": "Umbriel — Easy-going"},
    {"name": "Algieba", "label": "Algieba — Smooth"},
    {"name": "Despina", "label": "Despina — Smooth"},
    {"name": "Erinome", "label": "Erinome — Clear"},
    {"name": "Algenib", "label": "Algenib — Gravelly"},
    {"name": "Rasalgethi", "label": "Rasalgethi — Informative"},
    {"name": "Laomedeia", "label": "Laomedeia — Upbeat"},
    {"name": "Achernar", "label": "Achernar — Soft"},
    {"name": "Alnilam", "label": "Alnilam — Firm"},
    {"name": "Schedar", "label": "Schedar — Even"},
    {"name": "Gacrux", "label": "Gacrux — Mature"},
    {"name": "Pulcherrima", "label": "Pulcherrima — Forward"},
    {"name": "Achird", "label": "Achird — Friendly"},
    {"name": "Zubenelgenubi", "label": "Zubenelgenubi — Casual"},
    {"name": "Vindemiatrix", "label": "Vindemiatrix — Gentle"},
    {"name": "Sadachbia", "label": "Sadachbia — Lively"},
    {"name": "Sadaltager", "label": "Sadaltager — Knowledgeable"},
    {"name": "Sulafat", "label": "Sulafat — Warm"},
]
VOICE_NAMES = {v["name"] for v in VOICE_OPTIONS}


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "erro": str(message)}), status


def get_json_body():
    return request.get_json(silent=True) or {}


def get_client():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não foi configurada no Render.")
    return genai.Client(api_key=GEMINI_API_KEY)


def response_text(response) -> str:
    return getattr(response, "text", None) or ""


def safe_temperature(value) -> float:
    try:
        temp = float(value)
    except Exception:
        temp = 1.0
    return max(0.2, min(1.7, temp))


def text_config(temperature=1.0, max_output_tokens=4000):
    return types.GenerateContentConfig(
        temperature=safe_temperature(temperature),
        max_output_tokens=max_output_tokens,
    )


def duration_word_range(minutos) -> tuple[int, int, str]:
    try:
        m = int(str(minutos).strip())
    except Exception:
        m = 2
    if m <= 1:
        return 125, 155, "1 minuto"
    if m == 2:
        return 260, 320, "2 minutos"
    return 390, 470, "3 minutos"


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\wÀ-ÿ']+\b", text or ""))


def build_prompt(idioma: str = "Português", minutos: str = "2") -> str:
    idioma = (idioma or "Português").strip()
    minimo, maximo, _label = duration_word_range(minutos)
    return f"""
Você é o especialista de copy da RapidPublishers AI Desk.
Gere todo o conteúdo em {idioma.upper()}.

REGRA PRINCIPAL DE TEMPO:
- A seção # COPY FINAL deve ter entre {minimo} e {maximo} palavras.
- Conte apenas as palavras da seção # COPY FINAL.
- Use essa faixa para medir a duração real da narração.
- NÃO escreva no texto que a copy tem 1, 2 ou 3 minutos.
- NÃO escreva contagem de palavras.
- Antes de entregar, faça uma autocorreção silenciosa: se # COPY FINAL passar de {maximo} palavras, corte e reescreva; se ficar abaixo de {minimo}, complete com narração útil.

DNA obrigatório da copy:
- Primeira linha forte, concreta e curiosa. Evite começos genéricos.
- Segunda linha com motivo claro para continuar assistindo.
- CTA de salvar no início ou meio inicial, sem soar forçado.
- CTA de compartilhar em momento natural.
- Pergunta de cidade/país no meio da copy.
- Final com CTA pedindo nota de 0 a 10.
- Se houver cenas longas de preparo, distribua a narração, mas respeite a faixa de palavras.
- Cortar CTAs repetidos, agradecimentos longos e frases vazias.
- Evitar a expressão "comprado pronto" e comparações com produto pronto.
- Público principal: adulto, culinária caseira, linguagem clara, intensa e viral.

Entregue exatamente nesta estrutura:

# TÍTULOS CURTOS
- 5 opções curtas e fortes.

# COPY FINAL
Texto narrado, com frases curtas, bem distribuídas e pronto para áudio.

# LISTA DE INGREDIENTES
Ingredientes em lista clara. Se houver forno, geladeira ou tempo, incluir em letras MAIÚSCULAS.

# DESCRIÇÃO SEO
Descrição curta com palavras-chave naturais.

# HASHTAGS
8 a 12 hashtags relevantes.
""".strip()


def extract_section(text: str, section_name: str) -> str:
    if not text:
        return ""
    pattern = re.compile(rf"^\s*#\s*{re.escape(section_name)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^\s*#\s+.+$", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip("\n :-")


def extract_copy_final(text: str) -> str:
    section = extract_section(text, "COPY FINAL")
    return section or (text or "").strip()


def enforce_duration_once(client, resposta: str, idioma: str, minutos: str, temperature=1.0) -> str:
    minimo, maximo, _label = duration_word_range(minutos)
    copy = extract_copy_final(resposta)
    words = count_words(copy)
    if minimo <= words <= maximo:
        return resposta

    prompt = f"""
A resposta abaixo tem uma seção # COPY FINAL com {words} palavras, mas precisa ficar entre {minimo} e {maximo} palavras.
Reescreva a resposta completa em {idioma.upper()} mantendo a mesma estrutura:
# TÍTULOS CURTOS
# COPY FINAL
# LISTA DE INGREDIENTES
# DESCRIÇÃO SEO
# HASHTAGS

Regras:
- Ajuste SOMENTE o tamanho real da # COPY FINAL para ficar entre {minimo} e {maximo} palavras.
- Não mencione tempo, duração ou contagem de palavras.
- Não tire CTAs essenciais do DNA RapidPublishers.
- Mantenha frases curtas e prontas para áudio.

RESPOSTA BASE:
{resposta}
""".strip()
    fixed = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=text_config(temperature=temperature, max_output_tokens=4000),
    )
    return response_text(fixed) or resposta


def wait_for_file_ready(client, uploaded_file, timeout_seconds: int = 180):
    start = time.time()
    current = uploaded_file
    while True:
        state = getattr(current, "state", None)
        state_name = getattr(state, "name", None) or str(state or "")
        if "PROCESSING" not in state_name.upper():
            break
        if time.time() - start > timeout_seconds:
            raise TimeoutError("O arquivo demorou demais para processar no Gemini.")
        time.sleep(2)
        current = client.files.get(name=uploaded_file.name)

    state = getattr(current, "state", None)
    state_name = getattr(state, "name", None) or str(state or "")
    if "FAILED" in state_name.upper():
        raise RuntimeError("O Gemini não conseguiu processar este arquivo.")
    return current


def upload_file_to_gemini(client, path: str):
    uploaded = client.files.upload(file=path)
    return wait_for_file_ready(client, uploaded)


def safe_delete_gemini_file(client, uploaded_file):
    try:
        if uploaded_file and getattr(uploaded_file, "name", None):
            client.files.delete(name=uploaded_file.name)
    except Exception:
        pass


def download_best_audio(url: str, output_dir: str) -> str:
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("Cole um link válido começando com http ou https.")

    outtmpl = os.path.join(output_dir, "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 2,
        "socket_timeout": 30,
        "extractor_args": {"tiktok": {"api_hostname": ["api22-normal-c-useast1a.tiktokv.com"]}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = glob.glob(os.path.join(output_dir, "audio.*"))
    if not files:
        raise RuntimeError("Não consegui baixar o áudio do link informado. Se for TikTok bloqueado, baixe o vídeo e envie por upload.")
    return files[0]


def download_best_mp4(url: str, output_dir: str) -> str:
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("Cole um link válido começando com http ou https.")

    output_path = os.path.join(output_dir, "rapidpublishers_video.%(ext)s")
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "retries": 2,
        "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = glob.glob(os.path.join(output_dir, "rapidpublishers_video.*"))
    if not files:
        raise RuntimeError("Não consegui baixar o MP4 do link informado.")
    return files[0]


def pcm_to_wav_bytes(pcm: bytes, channels=1, rate=24000, sample_width=2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buffer.getvalue()


def clean_voice_name(voice: str) -> str:
    voice = (voice or "Achird").strip()
    return voice if voice in VOICE_NAMES else "Achird"


def build_tts_prompt(texto_audio: str, profile: str, style: str, pace: str, accent: str, tone: str) -> str:
    profile = (profile or "Narradora clara para vídeo de receita viral").strip()
    style = (style or "Natural, warm, confident, friendly, clear articulation").strip()
    pace = (pace or "Natural pace, not robotic, with small pauses between recipe steps").strip()
    accent = (accent or "Brazilian Portuguese, natural social media narration").strip()
    tone = (tone or "Human, expressive, appetizing, polished, not robotic").strip()
    return f"""
AUDIO PROFILE:
{profile}

DIRECTOR'S NOTES:
Style: {style}
Pace: {pace}
Accent: {accent}
Tone: {tone}
Performance: sound like a real food-content narrator. Keep it human, clear, smooth, and natural. Do not sound robotic. Use tasteful pauses between steps.

Read exactly the transcript below. Do not add introductions, comments, titles, explanations, or extra words.

TRANSCRIPT:
{texto_audio}
""".strip()


@app.route("/", methods=["GET"])
def home():
    if APP_HTML.exists():
        return send_from_directory(BASE_DIR, "gerador.html")
    return jsonify({"ok": True, "app": "RapidPublishers AI Desk", "status": "online"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "app": "RapidPublishers AI Desk",
        "status": "online",
        "sdk": "google-genai",
        "gemini_key_configurada": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL,
        "tts_model": GEMINI_TTS_MODEL,
    })


@app.route("/voices", methods=["GET"])
def voices():
    return jsonify({"ok": True, "voices": VOICE_OPTIONS})


@app.route("/debug-key", methods=["GET"])
def debug_key():
    return jsonify({
        "tem_chave": bool(GEMINI_API_KEY),
        "tamanho": len(GEMINI_API_KEY),
        "comeca_com": GEMINI_API_KEY[:4] if GEMINI_API_KEY else "",
        "sdk": "google-genai",
    })


@app.route("/processar", methods=["POST"])
def processar():
    try:
        client = get_client()

        if request.content_type and "multipart/form-data" in request.content_type:
            acao = request.form.get("acao", "upload")
            idioma = request.form.get("idioma", "Português")
            minutos = request.form.get("minutos", "2")
            temperature = request.form.get("temperature", "1.0")
            dados = {}
        else:
            dados = get_json_body()
            acao = dados.get("acao")
            idioma = dados.get("idioma", "Português")
            minutos = dados.get("minutos", "2")
            temperature = dados.get("temperature", 1.0)

        if acao == "video":
            url = (dados.get("url") or "").strip()
            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = download_best_audio(url, tmpdir)
                gemini_file = None
                try:
                    gemini_file = upload_file_to_gemini(client, audio_path)
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=[build_prompt(idioma, minutos), gemini_file],
                        config=text_config(temperature=temperature, max_output_tokens=5000),
                    )
                    resposta = response_text(response)
                    resposta = enforce_duration_once(client, resposta, idioma, minutos, temperature)
                    return jsonify({"ok": True, "resposta": resposta, "copy_words": count_words(extract_copy_final(resposta))})
                finally:
                    safe_delete_gemini_file(client, gemini_file)

        if acao == "upload":
            if "file" not in request.files:
                return json_error("Envie um arquivo de áudio ou vídeo.")

            file = request.files["file"]
            filename = secure_filename(file.filename or "arquivo")
            extension = Path(filename).suffix.lower()
            if extension and extension not in ALLOWED_UPLOAD_EXTENSIONS:
                return json_error("Formato não aceito. Envie áudio ou vídeo: mp3, wav, m4a, mp4, mov ou webm.")

            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, filename or "arquivo_upload")
                file.save(path)
                gemini_file = None
                try:
                    gemini_file = upload_file_to_gemini(client, path)
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=[build_prompt(idioma, minutos), gemini_file],
                        config=text_config(temperature=temperature, max_output_tokens=5000),
                    )
                    resposta = response_text(response)
                    resposta = enforce_duration_once(client, resposta, idioma, minutos, temperature)
                    return jsonify({"ok": True, "resposta": resposta, "copy_words": count_words(extract_copy_final(resposta))})
                finally:
                    safe_delete_gemini_file(client, gemini_file)

        if acao == "tempo":
            texto = (dados.get("texto") or "").strip()
            if not texto:
                return json_error("Gere ou cole uma copy antes de ajustar o tempo.")
            minimo, maximo, _label = duration_word_range(minutos)
            prompt = f"""
Reescreva a resposta abaixo em {idioma.upper()} mantendo a estrutura completa:
# TÍTULOS CURTOS
# COPY FINAL
# LISTA DE INGREDIENTES
# DESCRIÇÃO SEO
# HASHTAGS

REGRA OBRIGATÓRIA:
- A seção # COPY FINAL precisa ter entre {minimo} e {maximo} palavras.
- Conte apenas as palavras da seção # COPY FINAL.
- Não mencione tempo, duração ou contagem de palavras.
- Se estiver longo, corte sem destruir as cenas principais.
- Se estiver curto, complete com narração útil e natural.
- Mantenha o DNA RapidPublishers: gancho forte, CTA de salvar, compartilhar, cidade/país no meio e nota de 0 a 10 no final.

RESPOSTA BASE:
{texto}
""".strip()
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=text_config(temperature=temperature, max_output_tokens=5000),
            )
            resposta = response_text(response)
            resposta = enforce_duration_once(client, resposta, idioma, minutos, temperature)
            return jsonify({"ok": True, "resposta": resposta, "copy_words": count_words(extract_copy_final(resposta))})

        return json_error("Ação inválida. Use: video, upload ou tempo.")

    except Exception as e:
        msg = str(e)
        if "tiktok" in msg.lower() or "unable to download" in msg.lower():
            msg = "Falhou ao buscar o vídeo. O TikTok/Reels pode bloquear servidores como o Render. Tente baixar o vídeo e enviar pelo upload. Detalhe: " + msg
        return json_error(msg, 500)


@app.route("/chat", methods=["POST"])
def chat():
    try:
        client = get_client()
        dados = get_json_body()
        texto = (dados.get("texto") or "").strip()
        pedido = (dados.get("pedido") or "").strip()
        idioma = dados.get("idioma", "Português")
        minutos = dados.get("minutos", "2")
        temperature = dados.get("temperature", 1.0)

        if not texto:
            return json_error("Gere ou cole uma copy antes de pedir ajuste.")
        if not pedido:
            return json_error("Escreva o ajuste que você quer.")

        minimo, maximo, _label = duration_word_range(minutos)
        prompt = f"""
Você é o editor de copy da RapidPublishers AI Desk.
Idioma: {idioma.upper()}.

Pedido do usuário:
{pedido}

Regra de duração:
- A seção # COPY FINAL precisa ficar entre {minimo} e {maximo} palavras.
- Não mencione tempo, duração ou contagem de palavras.

Copy atual:
{texto}

Aplique o pedido mantendo o DNA RapidPublishers.
Entregue a resposta completa, com as seções:
# TÍTULOS CURTOS
# COPY FINAL
# LISTA DE INGREDIENTES
# DESCRIÇÃO SEO
# HASHTAGS
""".strip()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=text_config(temperature=temperature, max_output_tokens=5000),
        )
        resposta = response_text(response)
        resposta = enforce_duration_once(client, resposta, idioma, minutos, temperature)
        return jsonify({"ok": True, "resposta": resposta, "copy_words": count_words(extract_copy_final(resposta))})
    except Exception as e:
        return json_error(str(e), 500)


@app.route("/gerar_audio", methods=["POST"])
def gerar_audio():
    try:
        client = get_client()
        dados = get_json_body()
        texto = (dados.get("texto") or "").strip()
        if not texto:
            return json_error("Informe o texto para gerar áudio.")

        texto_audio = extract_copy_final(texto) or texto
        voice = clean_voice_name(dados.get("voice"))
        profile = dados.get("profile", "Narradora clara para vídeo de receita viral")
        style = dados.get("style", "Natural, warm, confident, friendly, clear articulation")
        pace = dados.get("pace", "Natural pace, not robotic, with small pauses between recipe steps")
        accent = dados.get("accent", "Brazilian Portuguese, natural social media narration")
        tone = dados.get("tone", "Human, expressive, appetizing, polished, not robotic")

        prompt = build_tts_prompt(texto_audio, profile, style, pace, accent, tone)
        response = client.models.generate_content(
            model=GEMINI_TTS_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        )
                    )
                ),
            ),
        )

        part = response.candidates[0].content.parts[0]
        inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
        if not inline or not getattr(inline, "data", None):
            raise RuntimeError("O Gemini não retornou áudio. Tente outra voz ou reduza a copy.")

        pcm = inline.data
        if isinstance(pcm, str):
            pcm = base64.b64decode(pcm)
        wav_bytes = pcm_to_wav_bytes(pcm)
        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        return jsonify({
            "ok": True,
            "audio_base64": audio_b64,
            "mime_type": "audio/wav",
            "voice": voice,
            "tts_model": GEMINI_TTS_MODEL,
        })

    except Exception as e:
        return json_error("Erro ao gerar áudio Gemini TTS: " + str(e), 500)


@app.route("/baixar_mp4", methods=["POST"])
def baixar_mp4():
    try:
        dados = get_json_body()
        url = (dados.get("url") or "").strip()
        tmpdir_obj = tempfile.TemporaryDirectory()
        tmpdir = tmpdir_obj.name
        video_path = download_best_mp4(url, tmpdir)

        @after_this_request
        def cleanup(response):
            try:
                tmpdir_obj.cleanup()
            except Exception:
                pass
            return response

        return send_file(video_path, as_attachment=True, download_name="rapidpublishers_video.mp4")

    except Exception as e:
        return json_error(str(e), 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
