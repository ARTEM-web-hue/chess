import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
import httpx

app = FastAPI()

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

# Новые маршруты для PWA
@app.get("/manifest.json")
async def manifest():
    return FileResponse("static/manifest.json")

@app.get("/sw.js")
async def sw():
    return FileResponse("static/sw.js")

@app.get("/icon-192.png")
async def icon192():
    return FileResponse("static/icon-192.png")

@app.get("/icon-512.png")
async def icon512():
    return FileResponse("static/icon-512.png")

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                MESSAGES_URL,
                headers=headers,
                params={"select": "author,content", "order": "created_at.asc", "limit": 100}
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

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        MESSAGES_URL,
                        headers=headers,
                        json={"author": author, "content": content}
                    )
            except Exception as e:
                print("Save error:", e)

            for conn in connections[:]:
                try:
                    await conn.send_text(f'<b>{author}</b>: {content}')
                except:
                    if conn in connections:
                        connections.remove(conn)
    except WebSocketDisconnect:
        if websocket in connections:
            connections.remove(websocket)
