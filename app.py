import base64
import glob
import os
import tempfile
import time
from pathlib import Path

from flask import Flask, after_this_request, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from google import genai
from gtts import gTTS
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
APP_HTML = BASE_DIR / "gerador.html"

app = Flask(__name__, static_folder=None)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash").strip()

ALLOWED_UPLOAD_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".mp4", ".mov", ".webm", ".mkv", ".avi"
}


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


def build_prompt(idioma: str = "Português", minutos: str = "2") -> str:
    idioma = (idioma or "Português").strip()
    minutos = str(minutos or "2").strip()
    return f"""
Você é o especialista de copy da RapidPublishers AI Desk.
Gere todo o conteúdo em {idioma.upper()}.

Objetivo de duração interna: aproximadamente {minutos} minuto(s).
IMPORTANTE: use essa duração apenas para calibrar o tamanho da narração. NÃO escreva no texto que a copy tem 1, 2 ou 3 minutos.

DNA obrigatório da copy:
- Primeira linha forte, concreta e curiosa. Evite começos genéricos.
- Segunda linha com motivo claro para continuar assistindo.
- CTA de salvar no início ou meio inicial, sem soar forçado.
- CTA de compartilhar em momento natural.
- Pergunta de cidade/país no meio da copy.
- Final com CTA pedindo nota de 0 a 10.
- Manter ritmo de vídeo: não encurtar demais cenas longas como cortar, misturar, empanar, abrir massa, fritar, virar, despejar creme, colocar na forma, desenformar e finalizar.
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


def extract_copy_final(text: str) -> str:
    """Tenta pegar só a seção COPY FINAL para gerar áudio."""
    if not text:
        return ""
    upper = text.upper()
    start_marker = "# COPY FINAL"
    start = upper.find(start_marker)
    if start == -1:
        return text.strip()
    start = start + len(start_marker)

    next_markers = ["# LISTA DE INGREDIENTES", "# DESCRIÇÃO SEO", "# HASHTAGS", "# TITULOS", "# TÍTULOS"]
    end_positions = []
    for marker in next_markers:
        pos = upper.find(marker, start)
        if pos != -1:
            end_positions.append(pos)
    end = min(end_positions) if end_positions else len(text)
    return text[start:end].strip("\n :-")


def wait_for_file_ready(client, uploaded_file, timeout_seconds: int = 120):
    """Aguarda arquivo processar quando o SDK expõe estado do arquivo."""
    start = time.time()
    current = uploaded_file
    while True:
        state = getattr(current, "state", None)
        state_name = getattr(state, "name", None) or str(state or "")
        state_name = state_name.upper()
        if "PROCESSING" not in state_name:
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


def gtts_lang(idioma: str) -> str:
    idioma = (idioma or "").lower()
    if "espan" in idioma or "span" in idioma:
        return "es"
    if "ingl" in idioma or "engl" in idioma:
        return "en"
    if "fran" in idioma or "fren" in idioma:
        return "fr"
    if "ital" in idioma:
        return "it"
    return "pt"


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
    })


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
            dados = {}
        else:
            dados = get_json_body()
            acao = dados.get("acao")
            idioma = dados.get("idioma", "Português")
            minutos = dados.get("minutos", "2")

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
                    )
                    return jsonify({"ok": True, "resposta": response_text(response)})
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
                    )
                    return jsonify({"ok": True, "resposta": response_text(response)})
                finally:
                    safe_delete_gemini_file(client, gemini_file)

        if acao == "tempo":
            texto = (dados.get("texto") or "").strip()
            if not texto:
                return json_error("Gere ou cole uma copy antes de ajustar o tempo.")

            prompt = f"""
Reescreva a copy abaixo em {idioma.upper()}, usando aproximadamente {minutos} minuto(s) apenas como referência interna de tamanho.
Não diga no texto que a copy tem essa duração.
Mantenha o DNA RapidPublishers: gancho forte, CTA de salvar, compartilhar, cidade/país no meio e nota de 0 a 10 no final.
Não resuma demais cenas longas de preparo.

COPY BASE:
{texto}
""".strip()
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return jsonify({"ok": True, "resposta": response_text(response)})

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

        if not texto:
            return json_error("Gere ou cole uma copy antes de pedir ajuste.")
        if not pedido:
            return json_error("Escreva o ajuste que você quer.")

        prompt = f"""
Você é o editor de copy da RapidPublishers AI Desk.
Idioma: {idioma.upper()}.
Duração interna desejada: aproximadamente {minutos} minuto(s), sem mencionar essa duração no texto.

Pedido do usuário:
{pedido}

Copy atual:
{texto}

Aplique o pedido mantendo o DNA RapidPublishers.
Entregue a copy ajustada completa, organizada e pronta para narrar.
""".strip()
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return jsonify({"ok": True, "resposta": response_text(response)})
    except Exception as e:
        return json_error(str(e), 500)


@app.route("/gerar_audio", methods=["POST"])
def gerar_audio():
    try:
        dados = get_json_body()
        texto = (dados.get("texto") or "").strip()
        idioma = dados.get("idioma", "Português")
        if not texto:
            return json_error("Informe o texto para gerar áudio.")

        texto_audio = extract_copy_final(texto)
        if not texto_audio:
            texto_audio = texto

        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = os.path.join(tmpdir, "rapidpublishers_audio.mp3")
            tts = gTTS(text=texto_audio, lang=gtts_lang(idioma), slow=False)
            tts.save(mp3_path)
            with open(mp3_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        return jsonify({"ok": True, "audio_base64": audio_b64, "mime_type": "audio/mpeg"})

    except Exception as e:
        return json_error("Erro ao gerar áudio: " + str(e), 500)


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
