import os
import glob
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

@app.route('/transcrever', methods=['POST'])
def transcrever():
    dados = request.get_json()
    url_video = dados.get('url')
    idioma_escolhido = dados.get('idioma', 'Espanhol') # Recebe o idioma do seu HTML
    
    if not url_video:
        return jsonify({'erro': 'Nenhum link fornecido'}), 400

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'audio.%(ext)s',
            'quiet': True,
            'noplaylist': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url_video])
            
        arquivo_audio = glob.glob("audio.*")[0]
        audio_file = genai.upload_file(path=arquivo_audio)
        
        # O prompt agora se adapta dinamicamente ao idioma escolhido
        prompt = f"""
        Atue como um copywriter e estrategista de conteúdo focado em vídeos culinários (estética 'food porn').
        Ouça o áudio deste vídeo e faça o seguinte:
        1. Extraia a receita completa e escreva-a rigorosamente em {idioma_escolhido.upper()}, com os ingredientes e o passo a passo bem estruturados.
        2. Crie uma legenda (copy) persuasiva, também em {idioma_escolhido.upper()}, com um gancho forte nas primeiras linhas para prender a atenção e maximizar a retenção do público.
        """
        
        model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")
        response = model.generate_content([prompt, audio_file])
        
        copy_final = response.text
        
        genai.delete_file(audio_file.name)
        os.remove(arquivo_audio)

        return jsonify({'copy': copy_final})

    except Exception as e:
        for f in glob.glob("audio.*"):
            os.remove(f)
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
