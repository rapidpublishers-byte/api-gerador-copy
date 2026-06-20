import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # Libera o acesso da sua página na Hostinger

@app.route('/transcrever', methods=['POST'])
def transcrever():
    dados = request.get_json()
    url_video = dados.get('url')
    
    if not url_video:
        return jsonify({'erro': 'Nenhum link fornecido'}), 400

    try:
        # A lógica real da IA entrará aqui nas próximas etapas.
        # Por enquanto, ele apenas devolve uma mensagem de sucesso para testarmos a conexão.
        
        texto_simulado = f"Sucesso! O link recebido foi: {url_video}\n\nAqui entrará a sua copy persuasiva gerada pela Inteligência Artificial."
        
        return jsonify({'copy': texto_simulado})

    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
