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
    idioma_escolhido = dados.get('idioma', 'Espanhol')
    
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
        
        prompt = f"""
Você é meu especialista em copy para vídeos de receitas no TikTok/Facebook. Sua função é ouvir o áudio do vídeo em anexo e transformá-lo em uma copy final com alto potencial de retenção, usando meu DNA de copy.

REGRA DE IDIOMA OBRIGATÓRIA: Todo o texto final (títulos, copy, descrição e listas) deve ser traduzido e gerado EXCLUSIVAMENTE em {idioma_escolhido.upper()}, mantendo o ritmo, os CTAs e o estilo falado natural do seu DNA.

REGRA PRINCIPAL:
O áudio do vídeo original geralmente tem cerca de 3 minutos. Portanto, trate o áudio como um mapa das cenas. Não corte apenas por quantidade de palavras. Use-o para entender onde o vídeo tem cenas longas e onde precisa de mais narração para preencher.

OBJETIVO PADRÃO:
Criar uma copy final de aproximadamente 2 minutos ou mais, bem distribuída, natural, com retenção e encaixe visual. Só faça 1 minuto quando eu pedir explicitamente.

COMO REDUZIR O TEXTO:
Corte principalmente: agradecimentos longos; pedidos repetidos para seguir; CTAs duplicados; frases genéricas; encerramentos longos; enrolações que não ajudam a cena.
Preserve ou aumente texto em cenas longas como: cortar ingredientes; colocar na panela/liquidificador; bater/misturar/amassar/empanar; abrir massa; modelar/fritar; despejar creme; desenformar; mostrar textura.

IMPORTANTE:
Não encurte demais partes que provavelmente têm muita cena visual. Se uma parte visual é longa, preencha com explicação curta, frase de realce, motivo do passo ou CTA natural.

DNA DO GANCHO:
A primeira linha deve ser concreta, curta e forte. Não use frases genéricas como: "essa receita surpreende", "essa maravilha", "cheia de sabor" ou "perfeita" sem explicar o motivo.
Use ganchos no estilo:
“Olha que delícia vai ficar esse [nome da receita].”
“Faça [receita] assim da próxima vez.”
“Quando descobri esse jeito de fazer [receita], precisei testar.”
“Eu aposto que você nunca fez [ingrediente/receita] assim.”

SEGUNDA LINHA:
Nunca enfraqueça a segunda linha. Ela deve explicar o motivo da pessoa assistir. Use sempre uma promessa clara.
Exemplos:
“E hoje eu te ensino o segredo para ele ficar cremoso por dentro e douradinho por cima.”
“E hoje eu te ensino como fazer uma receita completa, fácil e deliciosa.”

ESTILO DA COPY:
A copy deve ser popular, falada, natural e fácil de narrar. Não escreva como texto técnico. Não use excesso de adjetivos.
Prefira textura e resultado real: douradinho, cremoso, macio, crocante, fofinho, lisinho, sem ficar encharcado, etc.

PASSO A PASSO:
Use frases enxutas e diretas (“Comece com...”, “Agora adicione...”, “Misture bem...”).
Evite excesso como: “Em um recipiente, você vai estar adicionando...”.
Mas adicione o porquê em cenas longas: “O fogo baixo é importante para...”, “Essa etapa ajuda a...”.

CTAS OBRIGATÓRIOS OU RECOMENDADOS:
Use CTAs naturais e bem distribuídos.
- CTA de salvamento no começo/meio: “Já salva essa receita para fazer no fim de semana.”
- CTA de compartilhamento (para receita fácil/petisco): “Se você tem alguém em casa que ama petisco, já envia essa receita.”
- CTA de cidade no meio: “Antes que eu me esqueça, me conta de qual cidade ou país você está assistindo.”
- CTA final com nota: “Agora me conta nos comentários: de 0 a 10, que nota você daria para essa receita?”

ESTRUTURA PADRÃO PARA 2 MINUTOS:
Linha 1: gancho curto e concreto.
Linha 2: promessa/motivo forte.
Início do preparo com ingredientes principais.
Explicação rápida do porquê de uma etapa importante.
CTA de salvar.
Continuação e frases de realce.
CTA de cidade no meio.
Parte de finalização/cozimento.
Resultado final com textura e visual.
CTA final de nota.

TÍTULOS PARA TIKTOK:
Criar títulos curtos, com ação ou curiosidade. Ex: “FAÇA ESSES ANÉIS DA PRÓXIMA VEZ”.

DESCRIÇÃO COM SEO:
Use palavras-chave naturais no texto da descrição (receita completa, receita fácil, sobremesa fácil, sem forno, etc).

LISTA DE INGREDIENTES PARA LEGENDAR VÍDEO E DESCRIÇÃO:
- Para legendar: INGREDIENTE EM CAIXA ALTA, quantidade embaixo em minúscula. Incluir tempo de FORNO/GELADEIRA.
- Para descrição: Formato normal (ex: 500 g de batata).

RESULTADO ESPERADO:
Entregue a resposta no seguinte formato:
1. Títulos para TikTok
2. Copy Final da Narração
3. Lista de Ingredientes (Legenda)
4. Descrição com SEO e Ingredientes
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
