import tkinter as tk
import paho.mqtt.client as mqtt
import random
import json
import queue

# --- Configurações ---
BROKER = 'localhost'
PORT = 1883
TOPICO_LOBBY_BUSCA = "jogo/lobby/busca"
TOPICO_RESPOSTA = "jogo/match/resposta/{}"
TOPICO_RESULTADO = "jogo/match/resultado/{}"
TOPICO_MOVIMENTO = "jogo/partida/{}/movimento"
TOPICO_STATUS_CLIENTE = "jogo/cliente/status"
CLIENT_ID = f"jogador_{random.randint(100, 999)}"

MOVEMENT_STEP = 20
LARGURA_TELA = 600
ALTURA_TELA = 400

# Estados Globais
estado_jogo = "INICIO"
partida_atual = {}
evento_queue = queue.Queue()
other_players_elements = {}
meu_jogador_element = None
posicao_atual = {"x": 0, "y": 0}

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"({CLIENT_ID}) Conectado ao broker")
        client.subscribe("jogo/match/proposta/+")
    else:
        print(f"Falha conexao: {rc}")

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode()
        mensagem = json.loads(payload_str)
        
        if msg.topic.startswith("jogo/match/proposta/"):
            if CLIENT_ID in mensagem.get("jogadores", []):
                evento_queue.put(("PARTIDA_PROPOSTA", mensagem))
        
        elif msg.topic.startswith("jogo/match/resultado/"):
            # Verifica se é desta partida (se tivermos uma em vista)
            match_id_msg = msg.topic.split("/")[-1]
            if partida_atual and match_id_msg == partida_atual.get("match_id"):
                evento_queue.put(("RESULTADO_PARTIDA", mensagem))
                
        elif msg.topic.startswith("jogo/partida/"):
            if mensagem.get('id') != CLIENT_ID:
                evento_queue.put(("MOVIMENTO_OPONENTE", mensagem))
    except Exception as e:
        print(f"Erro msg: {e}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
client.on_connect = on_connect
client.on_message = on_message
lwt_payload = json.dumps({"id": CLIENT_ID, "status": "offline"})
client.will_set(TOPICO_STATUS_CLIENTE, payload=lwt_payload, qos=1, retain=False)
client.connect(BROKER, PORT, 60)
client.loop_start()

# --- Interface Tkinter ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Jogo MQTT - {CLIENT_ID}")
        self.geometry(f"{LARGURA_TELA}x{ALTURA_TELA}")
        self.resizable(False, False)
        
        self.canvas = tk.Canvas(self, width=LARGURA_TELA, height=ALTURA_TELA, bg="black")
        self.canvas.pack()
        
        self.bind("<w>", lambda e: self.mover(0, MOVEMENT_STEP))
        self.bind("<s>", lambda e: self.mover(0, -MOVEMENT_STEP))
        self.bind("<a>", lambda e: self.mover(-MOVEMENT_STEP, 0))
        self.bind("<d>", lambda e: self.mover(MOVEMENT_STEP, 0))
        
        self.mostrar_tela_inicial()
        self.processar_eventos()

    def cartesian_to_screen(self, x, y):
        screen_x = (LARGURA_TELA / 2) + x
        screen_y = (ALTURA_TELA / 2) - y 
        return screen_x, screen_y

    def limpar_ui(self):
        self.canvas.delete("ui")
        self.canvas.delete("game")

    def mostrar_tela_inicial(self):
        self.limpar_ui()
        self.canvas.configure(bg="black")
        self.canvas.create_text(LARGURA_TELA/2, 100, text="Jogo das Bolinhas", fill="white", font=("Arial", 24, "bold"), tags="ui")
        self.canvas.create_text(LARGURA_TELA/2, 140, text=f"ID: {CLIENT_ID}", fill="gray", font=("Arial", 12), tags="ui")
        
        btn_x, btn_y = LARGURA_TELA/2, 250
        self.canvas.create_rectangle(btn_x-80, btn_y-25, btn_x+80, btn_y+25, fill="gray", outline="white", tags=("ui", "btn_buscar"))
        self.canvas.create_text(btn_x, btn_y, text="Buscar Partida", fill="white", font=("Arial", 14), tags=("ui", "btn_buscar"))
        self.canvas.tag_bind("btn_buscar", "<Button-1>", self.acao_buscar_partida)

    def mostrar_tela_busca(self):
        self.limpar_ui()
        self.canvas.create_text(LARGURA_TELA/2, 200, text="Procurando Oponente...", fill="yellow", font=("Arial", 20), tags="ui")

    def mostrar_tela_confirmacao(self):
        self.limpar_ui()
        self.canvas.create_text(LARGURA_TELA/2, 100, text="Partida Encontrada!", fill="white", font=("Arial", 24), tags="ui")
        
        self.canvas.create_rectangle(200-60, 250-25, 200+60, 250+25, fill="green", tags=("ui", "btn_aceitar"))
        self.canvas.create_text(200, 250, text="Aceitar", fill="white", tags=("ui", "btn_aceitar"))
        self.canvas.tag_bind("btn_aceitar", "<Button-1>", self.acao_aceitar)

        self.canvas.create_rectangle(400-60, 250-25, 400+60, 250+25, fill="red", tags=("ui", "btn_recusar"))
        self.canvas.create_text(400, 250, text="Recusar", fill="white", tags=("ui", "btn_recusar"))
        self.canvas.tag_bind("btn_recusar", "<Button-1>", self.acao_recusar)

    def iniciar_ambiente_jogo(self, dados):
        self.limpar_ui()
        self.canvas.configure(bg="green")
        
        jogadores_info = dados["jogadores_info"]
        global meu_jogador_element, other_players_elements, posicao_atual
        other_players_elements = {}
        
        for pid, info in jogadores_info.items():
            cx, cy = self.cartesian_to_screen(info["posicao"][0], info["posicao"][1])
            cor = info["cor"]
            raio = 10
            elem = self.canvas.create_oval(cx-raio, cy-raio, cx+raio, cy+raio, fill=cor, tags="game")
            
            if pid == CLIENT_ID:
                meu_jogador_element = elem
                posicao_atual = {"x": info["posicao"][0], "y": info["posicao"][1]}
            else:
                other_players_elements[pid] = elem

        match_id = dados["match_id"]
        client.subscribe(TOPICO_MOVIMENTO.format(match_id))

    def mostrar_aviso_game_over(self, motivo):
        self.limpar_ui()
        self.canvas.configure(bg="#330000") # Fundo vermelho escuro
        self.canvas.create_text(LARGURA_TELA/2, 150, text="FIM DE JOGO", fill="red", font=("Arial", 30, "bold"), tags="ui")
        self.canvas.create_text(LARGURA_TELA/2, 200, text=motivo, fill="white", font=("Arial", 14), tags="ui")
        
        # Botão voltar
        self.canvas.create_rectangle(LARGURA_TELA/2-60, 300-20, LARGURA_TELA/2+60, 300+20, fill="gray", tags=("ui", "btn_voltar"))
        self.canvas.create_text(LARGURA_TELA/2, 300, text="Voltar ao Menu", fill="white", tags=("ui", "btn_voltar"))
        self.canvas.tag_bind("btn_voltar", "<Button-1>", lambda e: self.mostrar_tela_inicial())

    # --- Ações ---
    def acao_buscar_partida(self, event):
        global estado_jogo
        if estado_jogo == "INICIO":
            estado_jogo = "BUSCANDO"
            client.publish(TOPICO_LOBBY_BUSCA, json.dumps({"id": CLIENT_ID}))
            self.mostrar_tela_busca()

    def acao_aceitar(self, event):
        client.publish(TOPICO_RESPOSTA.format(partida_atual["match_id"]), json.dumps({"id": CLIENT_ID, "resposta": "aceito"}))
        self.canvas.create_text(LARGURA_TELA/2, 320, text="Aguardando...", fill="white", tags="ui")

    def acao_recusar(self, event):
        client.publish(TOPICO_RESPOSTA.format(partida_atual["match_id"]), json.dumps({"id": CLIENT_ID, "resposta": "recusado"}))
        self.mostrar_tela_inicial()

    def mover(self, dx, dy):
        global estado_jogo, posicao_atual
        if estado_jogo != "JOGANDO" or not meu_jogador_element: return
        posicao_atual["x"] += dx
        posicao_atual["y"] += dy
        sx, sy = self.cartesian_to_screen(posicao_atual["x"], posicao_atual["y"])
        raio = 10
        self.canvas.coords(meu_jogador_element, sx-raio, sy-raio, sx+raio, sy+raio)
        client.publish(TOPICO_MOVIMENTO.format(partida_atual["match_id"]), json.dumps({"id": CLIENT_ID, "x": posicao_atual["x"], "y": posicao_atual["y"]}))

    # --- Loop de Controle ---
    def processar_eventos(self):
        global estado_jogo, partida_atual
        try:
            while True:
                evento, dados = evento_queue.get_nowait()
                
                if evento == "PARTIDA_PROPOSTA" and estado_jogo == "BUSCANDO":
                    estado_jogo = "CONFIRMANDO"
                    partida_atual = dados
                    match_id = partida_atual["match_id"]
                    client.subscribe(TOPICO_RESULTADO.format(match_id))
                    self.mostrar_tela_confirmacao()
                    
                elif evento == "RESULTADO_PARTIDA":
                    # Se jogo vai começar
                    if dados["status"] == "iniciada":
                        estado_jogo = "JOGANDO"
                        partida_atual["jogadores_info"] = dados["jogadores_info"]
                        self.iniciar_ambiente_jogo(partida_atual)
                        
                    # Se jogo foi cancelado (no lobby)
                    elif dados["status"] == "cancelada" and estado_jogo == "CONFIRMANDO":
                        print("Cancelada no lobby")
                        estado_jogo = "INICIO"
                        client.unsubscribe(TOPICO_RESULTADO.format(partida_atual["match_id"]))
                        self.mostrar_tela_inicial()
                        
                    # NOVA LÓGICA: Se jogo foi encerrado ENQUANTO jogava
                    elif dados["status"] == "encerrada" and estado_jogo == "JOGANDO":
                        print("Jogo encerrado forçadamente.")
                        estado_jogo = "INICIO"
                        client.unsubscribe(TOPICO_MOVIMENTO.format(partida_atual["match_id"]))
                        client.unsubscribe(TOPICO_RESULTADO.format(partida_atual["match_id"]))
                        self.mostrar_aviso_game_over(dados.get("motivo", "Desconexão detectada."))
                        
                elif evento == "MOVIMENTO_OPONENTE":
                    if estado_jogo == "JOGANDO":
                        op_id = dados["id"]
                        if op_id in other_players_elements:
                            sx, sy = self.cartesian_to_screen(dados["x"], dados["y"])
                            r = 10
                            self.canvas.coords(other_players_elements[op_id], sx-r, sy-r, sx+r, sy+r)
        except queue.Empty:
            pass
        self.after(16, self.processar_eventos)

if __name__ == "__main__":
    app = App()
    app.mainloop()