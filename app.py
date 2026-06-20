import os
import glob
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
from openai import OpenAI

app = Flask(__name__)
CORS(app)

# Inicializa a IA (a chave será puxada do Render de forma segura)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@app.route('/transcrever', methods=['POST'])
def transcrever():
    dados = request.get_json()
    url_video = dados.get('url')
    
    if not url_video:
        return jsonify({'erro': 'Nenhum link fornecido'}), 400

    try:
        # 1. Baixar apenas o áudio do link (TikTok, YouTube, etc.)
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'audio.%(ext)s',
            'quiet': True,
            'noplaylist': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url_video])
            
        # Localiza o arquivo de áudio recém-baixado
        arquivo_audio = glob.glob("audio.*")[0]
        
        # 2. Transcrição Inteligente com Whisper
        with open(arquivo_audio, "rb") as audio_file:
            transcricao = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        texto_original = transcricao.text

        # 3. Engenharia de Prompt para a Copy
        prompt = f"""
        Atue como um copywriter e estrategista de conteúdo focado em vídeos culinários (estética 'food porn').
        Aqui está a transcrição bruta de um vídeo:
        "{texto_original}"
        
        Sua tarefa:
        1. Extraia a receita completa e reescreva-a EM ESPANHOL, com os ingredientes e o passo a passo bem estruturados.
        2. Crie uma legenda (copy) persuasiva, também em espanhol, com um gancho forte nas primeiras linhas para prender a atenção e maximizar a retenção.
        """
        
        # 4. Geração do Texto Final
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        
        copy_final = resposta.choices[0].message.content
        
        # Limpar o servidor apagando o arquivo de áudio temporário
        os.remove(arquivo_audio)

        return jsonify({'copy': copy_final})

    except Exception as e:
        # Garante que o arquivo seja apagado mesmo se houver erro
        for f in glob.glob("audio.*"):
            os.remove(f)
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
