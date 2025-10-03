import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import httpx

app = FastAPI()

# Получаем переменные из Render (они заданы в Environment)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

MESSAGES_URL = f"{SUPABASE_URL}/rest/v1/messages"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

connections = []

@app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)

    # Загружаем последние 100 сообщений
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                MESSAGES_URL,
                headers=headers,
                params={
                    "select": "author,content",
                    "order": "created_at.asc",
                    "limit": 100
                }
            )
            if r.status_code == 200:
                for msg in r.json():
                    await websocket.send_text(f'<b>{msg["author"]}</b>: {msg["content"]}')
    except Exception as e:
        print("Load error:", e)

    try:
        while True:
            data = await websocket.receive_text()
            if "|" not in data:
                continue
            author, content = data.split("|", 1)

            # Сохраняем в Supabase
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        MESSAGES_URL,
                        headers=headers,
                        json={"author": author, "content": content}
                    )
            except Exception as e:
                print("Save error:", e)

            # Рассылаем всем
            for conn in connections[:]:
                try:
                    await conn.send_text(f'<b>{author}</b>: {content}')
                except:
                    connections.remove(conn)
    except WebSocketDisconnect:
        if websocket in connections:
            connections.remove(websocket)
