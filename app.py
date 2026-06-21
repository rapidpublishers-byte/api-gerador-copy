import base64
import glob
import os
import tempfile
import time
from pathlib import Path

import yt_dlp
from flask import Flask, after_this_request, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from google import genai
from google.genai import types
from werkzeug.utils import secure_filename

# =========================================================
# RapidPublishers AI Desk - Backend compatível com novas keys AQ.*
# SDK: google-genai
# Variáveis no Render:
# GEMINI_API_KEY=sua_chave_do_Google_AI_Studio
# GEMINI_MODEL=gemini-2.5-flash              opcional
# GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview  opcional
# PORT=5000                                  opcional
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
APP_HTML = BASE_DIR / "gerador.html"

app = Flask(__name__, static_folder=None)
CORS(app)

api_key = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview").strip()

ALLOWED_UPLOAD_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".mp4", ".mov", ".webm", ".mkv", ".avi"
}


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "erro": message}), status


def require_gemini_key():
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não foi configurada no servidor.")


def get_client():
    require_gemini_key()
    return genai.Client(api_key=api_key)


def get_json_body():
    return request.get_json(silent=True) or {}


def build_prompt(idioma: str = "Espanhol") -> str:
    idioma = (idioma or "Espanhol").strip()
    return f"""
Você é o especialista de copy da RapidPublishers AI Desk.
Gere todo o conteúdo em {idioma.upper()}.

DNA obrigatório da copy:
- Primeira linha forte, concreta e curiosa. Evite começos genéricos.
- Segunda linha com motivo claro para continuar assistindo.
- Inserir CTA de salvar no início ou meio inicial, sem soar forçado.
- Inserir CTA de compartilhar em momento natural.
- Inserir pergunta de cidade/país no meio da copy.
- Finalizar com CTA pedindo nota de 0 a 10.
- Manter ritmo de vídeo: não encurtar demais cenas longas como cortar, misturar, empanar, abrir massa, fritar, virar, despejar creme, colocar na forma, desenformar e finalizar.
- Cortar principalmente CTAs repetidos, agradecimentos longos e frases vazias.
- Evitar a expressão "comprado pronto" e comparações com produto pronto.
- Público principal: adulto, culinária caseira, linguagem clara, intensa e viral.

Entregue exatamente nesta estrutura:

# TÍTULOS CURTOS
- 5 opções curtas e fortes.

# COPY FINAL
Texto narrado, com frases curtas, bem distribuídas e pronto para áudio.

# LISTA DE INGREDIENTES
Ingredientes em lista clara. Se houver forno, geladeira ou tempo, incluir em letras maiúsculas.

# DESCRIÇÃO SEO
Descrição curta com palavras-chave naturais.

# HASHTAGS
8 a 12 hashtags relevantes.
""".strip()


def wait_for_gemini_file(client, uploaded_file, timeout_seconds: int = 180):
    start = time.time()
    current = uploaded_file

    while getattr(current, "state", None) and str(current.state.name).upper() == "PROCESSING":
        if time.time() - start > timeout_seconds:
            raise TimeoutError("O arquivo demorou demais para processar no Gemini.")
        time.sleep(3)
        current = client.files.get(name=current.name)

    if getattr(current, "state", None) and str(current.state.name).upper() == "FAILED":
        raise RuntimeError("O Gemini não conseguiu processar este arquivo.")

    return current


def upload_file_to_gemini(client, path: str):
    uploaded = client.files.upload(file=path)
    return wait_for_gemini_file(client, uploaded)


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
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = glob.glob(os.path.join(output_dir, "audio.*"))
    if not files:
        raise RuntimeError("Não consegui baixar o áudio do link informado.")
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
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = glob.glob(os.path.join(output_dir, "rapidpublishers_video.*"))
    if not files:
        raise RuntimeError("Não consegui baixar o MP4 do link informado.")
    return files[0]


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
        "gemini_key_configurada": bool(api_key),
        "gemini_key_prefix": api_key[:4] if api_key else "",
        "gemini_model": GEMINI_MODEL,
    })


@app.route("/debug-key", methods=["GET"])
def debug_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    return jsonify({
        "tem_chave": bool(k),
        "comeca_com": k[:4] if k else "",
        "tamanho": len(k),
        "termina_com": k[-4:] if k else ""
    })


@app.route("/processar", methods=["POST"])
def processar():
    client = None
    gemini_file = None
    try:
        client = get_client()

        if request.content_type and "multipart/form-data" in request.content_type:
            acao = request.form.get("acao", "upload")
            idioma = request.form.get("idioma", "Espanhol")
            dados = {}
        else:
            dados = get_json_body()
            acao = dados.get("acao")
            idioma = dados.get("idioma", "Espanhol")

        if acao == "video":
            url = (dados.get("url") or "").strip()
            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = download_best_audio(url, tmpdir)
                try:
                    gemini_file = upload_file_to_gemini(client, audio_path)
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=[build_prompt(idioma), gemini_file]
                    )
                    return jsonify({"ok": True, "resposta": response.text or ""})
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
                try:
                    gemini_file = upload_file_to_gemini(client, path)
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=[build_prompt(idioma), gemini_file]
                    )
                    return jsonify({"ok": True, "resposta": response.text or ""})
                finally:
                    safe_delete_gemini_file(client, gemini_file)

        if acao == "tempo":
            minutos = str(dados.get("minutos") or "2").strip()
            texto = (dados.get("texto") or "").strip()
            if not texto:
                historico = dados.get("historico") or []
                if historico and isinstance(historico, list):
                    texto = str(historico[0].get("text", "")).strip()

            if not texto:
                return json_error("Cole ou gere uma copy antes de ajustar o tempo.")

            prompt = f"""
Reescreva a copy abaixo para aproximadamente {minutos} minuto(s), em {idioma.upper()}, mantendo o DNA RapidPublishers.
Não resuma demais cenas de preparo. Distribua a narração para preencher bem o vídeo.
Mantenha CTAs naturais: salvar, compartilhar, cidade/país no meio e nota de 0 a 10 no final.

COPY BASE:
{texto}
""".strip()
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return jsonify({"ok": True, "resposta": response.text or ""})

        return json_error("Ação inválida. Use: video, upload ou tempo.")

    except Exception as e:
        return json_error(str(e), 500)


@app.route("/gerar_audio", methods=["POST"])
def gerar_audio():
    try:
        client = get_client()
        dados = get_json_body()
        texto = (dados.get("texto") or "").strip()
        voz = (dados.get("voz") or "Achird").strip()

        if not texto:
            return json_error("Informe o texto para gerar áudio.")

        response = client.models.generate_content(
            model=GEMINI_TTS_MODEL,
            contents=texto,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voz
                        )
                    )
                )
            )
        )

        part = response.candidates[0].content.parts[0]
        inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
        if not inline:
            raise RuntimeError("O Gemini não retornou áudio.")

        audio_data = inline.data
        if isinstance(audio_data, bytes):
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        else:
            audio_b64 = str(audio_data)

        mime_type = getattr(inline, "mime_type", None) or getattr(inline, "mimeType", None) or "audio/wav"
        return jsonify({"ok": True, "audio_base64": audio_b64, "mime_type": mime_type})

    except Exception as e:
        return json_error(str(e), 500)


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
