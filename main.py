import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import httpx
from pywebpush import webpush, WebPushException
import json

app = FastAPI()

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# VAPID для Web Push
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
if not VAPID_PRIVATE_KEY:
    raise RuntimeError("VAPID_PRIVATE_KEY must be set in environment variables")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

# Глобальные хранилища
connections = []
push_subscriptions = []

MESSAGES_URL = f"{SUPABASE_URL}/rest/v1/messages"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# === Роуты ===

@app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

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

@app.post("/subscribe")
async def subscribe(request: Request):
    subscription = await request.json()
    endpoint = subscription.get("endpoint")
    if endpoint and not any(sub.get("endpoint") == endpoint for sub in push_subscriptions):
        push_subscriptions.append(subscription)
    return JSONResponse({"status": "ok"})

# === Push ===

def send_push_notification(author: str, content: str):
    message = f"{author}: {content[:80]}{'...' if len(content) > 80 else ''}"
    payload = json.dumps({
        "title": "Новое сообщение",
        "body": message
    })

    for sub in push_subscriptions[:]:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": "mailto:admin@onrender.com"}
            )
        except WebPushException as e:
            print("Push failed:", e)
            if e.response and e.response.status_code == 410:
                push_subscriptions.remove(sub)

# === WebSocket ===

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)

    # Загрузка истории — ПОМЕЧАЕМ как HISTORY
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                MESSAGES_URL,
                headers=headers,
                params={"select": "author,content", "order": "created_at.asc", "limit": 100}
            )
            if r.status_code == 200:
                for msg in r.json():
                    await websocket.send_text(f'HISTORY:<b>{msg["author"]}</b>: {msg["content"]}')
    except Exception as e:
        print("Load error:", e)

    # Новые сообщения
    try:
        while True:
            data = await websocket.receive_text()
            if "|" not in data:
                continue
            author, content = data.split("|", 1)

            send_push_notification(author, content)

            # Сохраняем в БД
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        MESSAGES_URL,
                        headers=headers,
                        json={"author": author, "content": content}
                    )
            except Exception as e:
                print("Save error:", e)

            # Рассылаем ВСЕМ (без HISTORY)
            for conn in connections[:]:
                try:
                    await conn.send_text(f'<b>{author}</b>: {content}')
                except:
                    if conn in connections:
                        connections.remove(conn)

    except WebSocketDisconnect:
        if websocket in connections:
            connections.remove(websocket)
