import paho.mqtt.client as mqtt
import json
import time
import random

# config
BROKER = 'localhost'
PORT = 2304
CLIENT_ID = "servidor_matchmaking_01"

# topicos do mosquito
TOPICO_LOBBY_BUSCA = "jogo/lobby/busca"
TOPICO_STATUS_CLIENTE = "jogo/cliente/status"
TOPICO_PROPOSTA = "jogo/match/proposta/{}"
TOPICO_RESPOSTA_WILDCRAD = "jogo/match/resposta/+"
TOPICO_RESULTADO = "jogo/match/resultado/{}"

POSICOES_INICIAIS = [(-200, 0), (0, 0), (200, 0)]
CORES_JOGO = ["red", "blue", "yellow"]

jogadores_na_fila = []
partidas_em_votacao = {}


def on_connect(client, userdata, flags, rc, properties=None):
    print("[Servidor] Conectado ao Broker MQTT com sucesso.")
    client.subscribe(TOPICO_LOBBY_BUSCA)
    client.subscribe(TOPICO_RESPOSTA_WILDCRAD)
    client.subscribe(TOPICO_STATUS_CLIENTE)
    print(f"[Servidor] Assinando tópicos de lobby, respostas e status de clientes.")

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
    if id_jogador and id_jogador not in jogadores_na_fila:
        jogadores_na_fila.append(id_jogador)
        print(f"[Servidor] Fila de espera atualizada: {jogadores_na_fila}")

    if len(jogadores_na_fila) >= 3:
        jogadores_da_partida = jogadores_na_fila[:3]
        
        jogadores_na_fila = [p for p in jogadores_na_fila if p not in jogadores_da_partida]
        
        print(f"[Servidor] Formando partida com: {jogadores_da_partida}")
        print(f"[Servidor] Fila de espera restante: {jogadores_na_fila}")

        match_id = f"partida_{random.randint(1000, 9999)}"
        topico_proposta_especifico = TOPICO_PROPOSTA.format(match_id)
        
        payload_proposta = {"match_id": match_id, "jogadores": jogadores_da_partida}
        client.publish(topico_proposta_especifico, json.dumps(payload_proposta))
        print(f"[Servidor] Proposta enviada no tópico: {topico_proposta_especifico}")

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
            print(f"[Servidor] Voto recebido para partida {match_id}: {id_jogador} votou '{resposta}'")
            verificar_estado_partida(client, match_id)

def handle_cliente_offline(client, mensagem):
    id_jogador_offline = mensagem.get("id")
    if not id_jogador_offline: return

    print(f"[Servidor] Recebido 'testamento' de {id_jogador_offline}. Ele desconectou.")

    if id_jogador_offline in jogadores_na_fila:
        jogadores_na_fila.remove(id_jogador_offline)
        print(f"[Servidor] {id_jogador_offline} removido da fila. Fila agora: {jogadores_na_fila}")

    match_a_cancelar = None
    for match_id, partida in partidas_em_votacao.items():
        if id_jogador_offline in partida["jogadores"]:
            match_a_cancelar = match_id
            break
    
    if match_a_cancelar:
        print(f"[Servidor] {id_jogador_offline} estava na partida {match_a_cancelar}. Cancelando a votação.")
        verificar_estado_partida(client, match_a_cancelar, jogador_saiu=id_jogador_offline)

def verificar_estado_partida(client, match_id, por_timeout=False, jogador_saiu=None):
    if match_id not in partidas_em_votacao:
        return

    partida = partidas_em_votacao[match_id]
    resultado_final = None

    if por_timeout:
        resultado_final = {"status": "cancelada", "motivo": "timeout"}
    elif jogador_saiu:
        resultado_final = {"status": "cancelada", "motivo": f"jogador {jogador_saiu} desconectou"}
    elif "recusado" in partida["respostas"].values():
        resultado_final = {"status": "cancelada", "motivo": "recusado"}
    elif len(partida["respostas"]) == len(partida["jogadores"]):
        if all(r == "aceito" for r in partida["respostas"].values()):
            jogadores_info = {}
            for i, jogador_id in enumerate(partida["jogadores"]):
                jogadores_info[jogador_id] = {
                    "posicao": POSICOES_INICIAIS[i],
                    "cor": CORES_JOGO[i]
                }
            resultado_final = {"status": "iniciada", "jogadores_info": jogadores_info}

    if resultado_final:
        resultado_final['match_id'] = match_id
        print(f"[Servidor] Partida {match_id} finalizada. Resultado: {resultado_final['status']}")
        topico_resultado_especifico = TOPICO_RESULTADO.format(match_id)
        client.publish(topico_resultado_especifico, json.dumps(resultado_final))
        
        if resultado_final["status"] == "cancelada":
            print(f"[Servidor] Jogadores da partida {match_id} foram liberados e devem buscar novamente.")
            
        del partidas_em_votacao[match_id]

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_start()

print("Servidor de Matchmaking iniciado.")
while True:
    for match_id in list(partidas_em_votacao.keys()):
        partida = partidas_em_votacao[match_id]
        if time.time() - partida["inicio_tempo"] > 10:
            print(f"[Servidor] Partida {match_id} excedeu o tempo limite!")
            verificar_estado_partida(client, match_id, por_timeout=True)
    time.sleep(1)