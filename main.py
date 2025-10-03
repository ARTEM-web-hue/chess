from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

# Все активные соединения
connections = []

@app.get("/")
async def get():
    with open("index.html") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Рассылаем всем (анонимно)
            for conn in connections:
                await conn.send_text(data)
    except WebSocketDisconnect:
        connections.remove(websocket)
