import paho.mqtt.client as mqtt
import json
import time
import random

# config
BROKER = 'localhost'
PORT = 1883
CLIENT_ID = "servidor_matchmaking_01"

# topicos
TOPICO_LOBBY_BUSCA = "jogo/lobby/busca"
TOPICO_STATUS_CLIENTE = "jogo/cliente/status"
TOPICO_PROPOSTA = "jogo/match/proposta/{}"
TOPICO_RESPOSTA_WILDCRAD = "jogo/match/resposta/+"
TOPICO_RESULTADO = "jogo/match/resultado/{}"

POSICOES_INICIAIS = [(-200, 0), (0, 0), (200, 0)]
CORES_JOGO = ["red", "blue", "yellow"]

jogadores_na_fila = []
partidas_em_votacao = {}
partidas_em_andamento = {}  # <--- NOVA ESTRUTURA: Guarda jogos que já começaram

def on_connect(client, userdata, flags, rc, properties=None):
    print("[Servidor] Conectado ao Broker MQTT com sucesso.")
    client.subscribe(TOPICO_LOBBY_BUSCA)
    client.subscribe(TOPICO_RESPOSTA_WILDCRAD)
    client.subscribe(TOPICO_STATUS_CLIENTE)

def on_message(client, userdata, msg):
    payload_str = msg.payload.decode()
    mensagem = json.loads(payload_str)
    
    if msg.topic == TOPICO_LOBBY_BUSCA:
        handle_busca_lobby(client, mensagem)
    elif msg.topic.startswith("jogo/match/resposta/"):
        handle_resposta_jogador(client, msg.topic, mensagem)
    elif msg.topic == TOPICO_STATUS_CLIENTE:
        if mensagem.get("status") == "offline":
            handle_cliente_offline(client, mensagem)

def handle_busca_lobby(client, mensagem):
    global jogadores_na_fila
    id_jogador = mensagem.get('id')
    
    # Se o jogador já estiver em partida, ignorar ou tratar reconexão (simplificado aqui)
    for p in partidas_em_andamento.values():
        if id_jogador in p["jogadores"]:
            print(f"[Servidor] {id_jogador} tentou buscar partida mas já está jogando.")
            return

    if id_jogador and id_jogador not in jogadores_na_fila:
        jogadores_na_fila.append(id_jogador)
        print(f"[Servidor] Fila: {jogadores_na_fila}")

    if len(jogadores_na_fila) >= 3:
        jogadores_da_partida = jogadores_na_fila[:3]
        jogadores_na_fila = [p for p in jogadores_na_fila if p not in jogadores_da_partida]
        
        match_id = f"partida_{random.randint(1000, 9999)}"
        topico_proposta = TOPICO_PROPOSTA.format(match_id)
        
        client.publish(topico_proposta, json.dumps({"match_id": match_id, "jogadores": jogadores_da_partida}))
        
        partidas_em_votacao[match_id] = {
            "jogadores": jogadores_da_partida,
            "respostas": {},
            "inicio_tempo": time.time()
        }

def handle_resposta_jogador(client, topic, mensagem):
    match_id = topic.split('/')[-1]
    id_jogador = mensagem.get('id')
    resposta = mensagem.get('resposta')

    if match_id in partidas_em_votacao:
        partida = partidas_em_votacao[match_id]
        if id_jogador not in partida["respostas"]:
            partida["respostas"][id_jogador] = resposta
            verificar_estado_partida(client, match_id)

def handle_cliente_offline(client, mensagem):
    id_jogador_offline = mensagem.get("id")
    if not id_jogador_offline: return

    print(f"[Servidor] {id_jogador_offline} desconectou.")

    # 1. Remover da fila se estiver lá
    if id_jogador_offline in jogadores_na_fila:
        jogadores_na_fila.remove(id_jogador_offline)

    # 2. Verificar se estava em VOTAÇÃO (Lobby)
    match_a_cancelar = None
    for match_id, partida in partidas_em_votacao.items():
        if id_jogador_offline in partida["jogadores"]:
            match_a_cancelar = match_id
            break
    if match_a_cancelar:
        print(f"[Servidor] Cancelando lobby {match_a_cancelar} por desconexão.")
        verificar_estado_partida(client, match_a_cancelar, jogador_saiu=id_jogador_offline)

    # 3. Verificar se estava em JOGO (Active Game) <--- NOVO
    match_em_curso_cancelar = None
    for match_id, partida in partidas_em_andamento.items():
        if id_jogador_offline in partida["jogadores"]:
            match_em_curso_cancelar = match_id
            break
    
    if match_em_curso_cancelar:
        print(f"[Servidor] Jogador caiu durante a partida {match_em_curso_cancelar}. Encerrando jogo para todos.")
        encerrar_partida_em_curso(client, match_em_curso_cancelar, id_jogador_offline)

def encerrar_partida_em_curso(client, match_id, culpado_id):
    # Envia mensagem para o tópico de resultado (que os clientes ainda escutam ou escutarão)
    payload = {
        "status": "encerrada", 
        "match_id": match_id,
        "motivo": f"O jogador {culpado_id} desconectou."
    }
    client.publish(TOPICO_RESULTADO.format(match_id), json.dumps(payload))
    
    # Remove da memória
    if match_id in partidas_em_andamento:
        del partidas_em_andamento[match_id]

def verificar_estado_partida(client, match_id, por_timeout=False, jogador_saiu=None):
    if match_id not in partidas_em_votacao: return

    partida = partidas_em_votacao[match_id]
    resultado_final = None

    if por_timeout:
        resultado_final = {"status": "cancelada", "motivo": "timeout"}
    elif jogador_saiu:
        resultado_final = {"status": "cancelada", "motivo": f"jogador {jogador_saiu} saiu"}
    elif "recusado" in partida["respostas"].values():
        resultado_final = {"status": "cancelada", "motivo": "recusado"}
    elif len(partida["respostas"]) == len(partida["jogadores"]):
        if all(r == "aceito" for r in partida["respostas"].values()):
            # Configurar início
            jogadores_info = {}
            for i, jogador_id in enumerate(partida["jogadores"]):
                jogadores_info[jogador_id] = {
                    "posicao": POSICOES_INICIAIS[i],
                    "cor": CORES_JOGO[i]
                }
            resultado_final = {"status": "iniciada", "jogadores_info": jogadores_info}
            
            # --- MUDANÇA CRUCIAL ---
            # Salva a partida como "Em Andamento" antes de remover da votação
            partidas_em_andamento[match_id] = {
                "jogadores": partida["jogadores"],
                "inicio": time.time()
            }
            # -----------------------

    if resultado_final:
        resultado_final['match_id'] = match_id
        client.publish(TOPICO_RESULTADO.format(match_id), json.dumps(resultado_final))
        del partidas_em_votacao[match_id]

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_start()

print("Servidor Matchmaking + Monitoramento Ativo.")
while True:
    # Limpeza de timeouts de lobby
    for match_id in list(partidas_em_votacao.keys()):
        partida = partidas_em_votacao[match_id]
        if time.time() - partida["inicio_tempo"] > 10:
            verificar_estado_partida(client, match_id, por_timeout=True)
    time.sleep(1)