import turtle
import paho.mqtt.client as mqtt
import random
import json
import queue
import time

# config
BROKER = 'localhost'
PORT = 2304
TOPICO_LOBBY_BUSCA = "jogo/lobby/busca"
TOPICO_RESPOSTA = "jogo/match/resposta/{}"
TOPICO_RESULTADO = "jogo/match/resultado/{}"
TOPICO_MOVIMENTO = "jogo/partida/{}/movimento"
TOPICO_STATUS_CLIENTE = "jogo/cliente/status"
CLIENT_ID = f"jogador_{random.randint(100, 999)}"

# estados
estado_jogo = "INICIO"
partida_atual = {}
evento_queue = queue.Queue()
head = None
other_players = {}
MOVEMENT_STEP = 20

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"({CLIENT_ID}) Conectado ao broker MQTT")
        client.subscribe("jogo/match/proposta/+")
    else:
        print(f"({CLIENT_ID}) Falha na conexao, codigo {rc}")

def on_message(client, userdata, msg):
    payload_str = msg.payload.decode()
    mensagem = json.loads(payload_str)
    
    if msg.topic.startswith("jogo/match/proposta/"):
        if CLIENT_ID in mensagem.get("jogadores", []):
            evento_queue.put(("PARTIDA_PROPOSTA", mensagem))
    elif msg.topic.startswith("jogo/match/resultado/"):
        if partida_atual and msg.topic == TOPICO_RESULTADO.format(partida_atual.get("match_id")):
            evento_queue.put(("RESULTADO_PARTIDA", mensagem))
    elif msg.topic.startswith("jogo/partida/"):
        if mensagem.get('id') != CLIENT_ID:
            evento_queue.put(("MOVIMENTO_OPONENTE", mensagem))

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
client.on_connect = on_connect
client.on_message = on_message
lwt_payload = json.dumps({"id": CLIENT_ID, "status": "offline"})
client.will_set(TOPICO_STATUS_CLIENTE, payload=lwt_payload, qos=1, retain=False)
client.connect(BROKER, PORT, 60)
client.loop_start()

def publicar_minha_posicao():
    if head:
        payload = {"id": CLIENT_ID, "x": head.xcor(), "y": head.ycor()}
        client.publish(TOPICO_MOVIMENTO.format(partida_atual["match_id"]), json.dumps(payload))

def go_up():
    if head: head.sety(head.ycor() + MOVEMENT_STEP); publicar_minha_posicao()
def go_down():
    if head: head.sety(head.ycor() - MOVEMENT_STEP); publicar_minha_posicao()
def go_left():
    if head: head.setx(head.xcor() - MOVEMENT_STEP); publicar_minha_posicao()
def go_right():
    if head: head.setx(head.xcor() + MOVEMENT_STEP); publicar_minha_posicao()

def buscar_partida(x, y):
    global estado_jogo
    if estado_jogo != "INICIO": return
    estado_jogo = "BUSCANDO"
    botao_buscar.hideturtle(); texto_botao.clear()
    payload = {"id": CLIENT_ID}
    client.publish(TOPICO_LOBBY_BUSCA, json.dumps(payload))
    texto_tela.clear(); texto_tela.write("Procurando partida...", align="center", font=("Arial", 24, "bold"))

def aceitar_partida(x, y):
    payload = {"id": CLIENT_ID, "resposta": "aceito"}
    client.publish(TOPICO_RESPOSTA.format(partida_atual["match_id"]), json.dumps(payload))
    esconder_botoes_confirmacao()

def cancelar_partida(x, y):
    payload = {"id": CLIENT_ID, "resposta": "recusado"}
    client.publish(TOPICO_RESPOSTA.format(partida_atual["match_id"]), json.dumps(payload))
    esconder_botoes_confirmacao()

def mostrar_tela_busca():
    global estado_jogo
    estado_jogo = "INICIO"
    esconder_botoes_confirmacao()
    texto_tela.clear()
    botao_buscar.showturtle()
    texto_botao.clear()
    texto_botao.write("Buscar Partida", align="center", font=("Arial", 16, "normal"))

def esconder_botoes_confirmacao():
    botao_aceitar.hideturtle(); texto_aceitar.clear()
    botao_cancelar.hideturtle(); texto_cancelar.clear()
    texto_tela.clear()
    texto_tela.write("Aguardando outros jogadores...", align="center", font=("Arial", 16, "bold"))

def iniciar_jogo(dados_partida):
    global head, other_players
    wn.clear(); wn.bgcolor("green"); wn.title(f"Jogo - {CLIENT_ID}")
    
    match_id = dados_partida["match_id"]
    client.subscribe(TOPICO_MOVIMENTO.format(match_id))

    jogadores_info = dados_partida["jogadores_info"]
    for jogador_id, info in jogadores_info.items():
        pos, cor = info["posicao"], info["cor"]
        nova_bolinha = turtle.Turtle()
        nova_bolinha.speed(0); nova_bolinha.shape("circle"); nova_bolinha.color(cor); nova_bolinha.penup(); nova_bolinha.goto(pos[0], pos[1])
        if jogador_id == CLIENT_ID: head = nova_bolinha
        else: other_players[jogador_id] = nova_bolinha

    wn.listen(); wn.onkeypress(go_up, "w"); wn.onkeypress(go_down, "s"); wn.onkeypress(go_left, "a"); wn.onkeypress(go_right, "d")

# --- Configuração da Tela ---
wn = turtle.Screen()
wn.title(f"Lobby - {CLIENT_ID}"); wn.bgcolor("black"); wn.setup(width=600, height=400); wn.tracer(0)
texto_tela = turtle.Turtle(); texto_tela.speed(0); texto_tela.color("white"); texto_tela.penup(); texto_tela.hideturtle(); texto_tela.goto(0, 50)
botao_buscar = turtle.Turtle(); botao_buscar.speed(0); botao_buscar.shape("square"); botao_buscar.color("grey"); botao_buscar.shapesize(stretch_wid=3, stretch_len=10); botao_buscar.penup(); botao_buscar.goto(0, -50)
texto_botao = turtle.Turtle(); texto_botao.speed(0); texto_botao.color("white"); texto_botao.penup()
texto_botao.goto(0, -65); texto_botao.write("Buscar Partida", align="center", font=("Arial", 16, "normal")); texto_botao.hideturtle()
botao_buscar.onclick(buscar_partida)
botao_aceitar = turtle.Turtle(); botao_aceitar.speed(0); botao_aceitar.shape("square"); botao_aceitar.color("green"); botao_aceitar.shapesize(stretch_wid=2.5, stretch_len=8); botao_aceitar.penup(); botao_aceitar.goto(-100, -50); botao_aceitar.hideturtle()
texto_aceitar = turtle.Turtle(); texto_aceitar.speed(0); texto_aceitar.color("white"); texto_aceitar.penup(); texto_aceitar.hideturtle(); texto_aceitar.goto(-100, -62)
botao_aceitar.onclick(aceitar_partida)
botao_cancelar = turtle.Turtle(); botao_cancelar.speed(0); botao_cancelar.shape("square"); botao_cancelar.color("red"); botao_cancelar.shapesize(stretch_wid=2.5, stretch_len=8); botao_cancelar.penup(); botao_cancelar.goto(100, -50); botao_cancelar.hideturtle()
texto_cancelar = turtle.Turtle(); texto_cancelar.speed(0); texto_cancelar.color("white"); texto_cancelar.penup(); texto_cancelar.hideturtle(); texto_cancelar.goto(100, -62)
botao_cancelar.onclick(cancelar_partida)
wn.update()

# --- Loop Principal ---
TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS
try:
    while True:
        frame_start_time = time.time()

        if estado_jogo != "JOGANDO":
            try:
                evento, dados = evento_queue.get(block=False)
                if evento == "PARTIDA_PROPOSTA" and estado_jogo == "BUSCANDO":
                    estado_jogo = "CONFIRMANDO"; partida_atual = dados; match_id = partida_atual["match_id"]
                    topico_resultado_especifico = TOPICO_RESULTADO.format(match_id)
                    client.subscribe(topico_resultado_especifico)
                    print(f"({CLIENT_ID}) Fui convidado! Assinando: {topico_resultado_especifico}")
                    texto_tela.clear(); texto_tela.write("Partida Encontrada!", align="center", font=("Arial", 24, "bold"))
                    botao_aceitar.showturtle(); texto_aceitar.clear(); texto_aceitar.write("Aceitar", align="center", font=("Arial", 16, "normal"))
                    botao_cancelar.showturtle(); texto_cancelar.clear(); texto_cancelar.write("Cancelar", align="center", font=("Arial", 16, "normal"))
                elif evento == "RESULTADO_PARTIDA":
                    match_id = dados["match_id"]
                    topico_resultado_especifico = TOPICO_RESULTADO.format(match_id)
                    client.unsubscribe(topico_resultado_especifico)
                    if dados["status"] == "iniciada":
                        estado_jogo = "JOGANDO"
                        partida_atual = {"match_id": dados["match_id"], "jogadores_info": dados["jogadores_info"]}
                        iniciar_jogo(partida_atual)
                    elif dados["status"] == "cancelada":
                        print(f"({CLIENT_ID}) Partida cancelada (Motivo: {dados['motivo']})")
                        mostrar_tela_busca()
            except queue.Empty:
                pass
        else:
            try:
                evento, dados = evento_queue.get(block=False)
                if evento == "MOVIMENTO_OPONENTE":
                    oponente_id = dados["id"]
                    if oponente_id in other_players:
                        other_players[oponente_id].goto(dados["x"], dados["y"])
            except queue.Empty:
                pass

        wn.update()
        elapsed_time = time.time() - frame_start_time
        time_to_wait = FRAME_TIME - elapsed_time
        if time_to_wait > 0:
            time.sleep(time_to_wait)
            
except turtle.Terminator:
    print(f"({CLIENT_ID}) Janela fechada. Encerrando...")
    client.loop_stop()
    client.disconnect()
    print(f"({CLIENT_ID}) Desconectado.")