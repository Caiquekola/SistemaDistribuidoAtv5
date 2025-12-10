import socket
client = socket.socket()
client.connect(('localhost', 5000))
client.send("Olá servidor!".encode())
client.settimeout(3)
try:
    data = client.recv(1024).decode()
except socket.timeout:
    print("Timeout: servidor não respondeu.")
print("Resposta:", data)
client.close()
