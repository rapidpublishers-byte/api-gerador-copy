import os
import glob
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import google.generativeai as genai
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/processar', methods=['POST'])
def processar():
    # Verifica se é um upload de arquivo (multipart/form-data) ou JSON normal
    if request.content_type and 'multipart/form-data' in request.content_type:
        acao = request.form.get('acao')
        idioma_escolhido = request.form.get('idioma', 'Espanhol')
    else:
        dados = request.get_json()
        acao = dados.get('acao')
        idioma_escolhido = dados.get('idioma', 'Espanhol')
    
    try:
        model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")
        prompt_base = f"""
Você é meu especialista em copy para vídeos de receitas. Sua função é transformar o áudio em anexo em uma copy final com alto potencial de retenção.
REGRA OBRIGATÓRIA: Todo o texto final deve ser gerado EXCLUSIVAMENTE em {idioma_escolhido.upper()}.
Siga rigorosamente meu DNA: gancho forte, promessa clara, frases curtas, foco na textura (cremoso, douradinho) e CTAs naturais.
Entregue: 1. Títulos Curtos / 2. Copy Final / 3. Lista de Ingredientes / 4. Descrição SEO.
"""
        
        # 1. PROCESSAR VÍDEO POR LINK
        if acao == 'video':
            url_video = dados.get('url')
            if not url_video: return jsonify({'erro': 'Link não fornecido'}), 400

            ydl_opts = {'format': 'bestaudio/best', 'outtmpl': 'audio.%(ext)s', 'quiet': True, 'noplaylist': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url_video])
                
            arquivo_audio = glob.glob("audio.*")[0]
            audio_file = genai.upload_file(path=arquivo_audio)
            
            chat = model.start_chat(history=[])
            response = chat.send_message([prompt_base, audio_file])
            
            genai.delete_file(audio_file.name)
            os.remove(arquivo_audio)
            return jsonify({'resposta': response.text})

        # 2. PROCESSAR UPLOAD DE ARQUIVO (MP3/MP4)
        elif acao == 'upload':
            if 'file' not in request.files: return jsonify({'erro': 'Nenhum arquivo enviado'}), 400
            file = request.files['file']
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            audio_file = genai.upload_file(path=filepath)
            chat = model.start_chat(history=[])
            response = chat.send_message([prompt_base, audio_file])
            
            genai.delete_file(audio_file.name)
            os.remove(filepath)
            return jsonify({'resposta': response.text})

        # 3. CHAT DE REFINAMENTO
        elif acao == 'texto':
            mensagem = dados.get('mensagem')
            historico_front = dados.get('historico', [])
            history_gemini = [{"role": msg["role"], "parts": [msg["text"]]} for msg in historico_front]
                
            chat = model.start_chat(history=history_gemini)
            response = chat.send_message(mensagem)
            return jsonify({'resposta': response.text})
            
        # 4. CONTROLE DE TEMPO (1, 2, 3 Minutos)
        elif acao == 'tempo':
            minutos = dados.get('minutos')
            historico_front = dados.get('historico', [])
            history_gemini = [{"role": msg["role"], "parts": [msg["text"]]} for msg in historico_front]
            
            comando = f"Reescreva a última copy gerada para que ela tenha o tamanho ideal para uma locução de exatamente {minutos} minuto(s). Mantenha o idioma {idioma_escolhido.upper()}."
            chat = model.start_chat(history=history_gemini)
            response = chat.send_message(comando)
            return jsonify({'resposta': response.text})

        else:
            return jsonify({'erro': 'Ação inválida'}), 400

    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/gerar_audio', methods=['POST'])
def gerar_audio():
    dados = request.get_json()
    texto = dados.get('texto')
    voz = dados.get('voz', 'Achird')
    temperatura = float(dados.get('temperatura', 1.0))
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": texto}]}],
        "generationConfig": {
            "temperature": temperatura,
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voz
                    }
                }
            }
        }
    }
    
    try:
        response = requests.post(url, json=payload)
        response_data = response.json()
        if 'error' in response_data: return jsonify({'erro': response_data['error']['message']}), 500
            
        audio_b64 = response_data['candidates'][0]['content']['parts'][0]['inlineData']['data']
        return jsonify({'audio_base64': audio_b64})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/baixar_mp4', methods=['POST'])
def baixar_mp4():
    dados = request.get_json()
    url = dados.get('url')
    if not url: return jsonify({'erro': 'Link não fornecido'}), 400

    try:
        # Baixa a melhor qualidade combinada de vídeo e áudio
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(UPLOAD_FOLDER, 'video_baixado.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'merge_output_format': 'mp4'
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Corrige a extensão caso o merge force para mp4
            if not filename.endswith('.mp4'):
                filename = filename.rsplit('.', 1)[0] + '.mp4'
                
        return send_file(filename, as_attachment=True, download_name='qualidade_maxima.mp4')
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
