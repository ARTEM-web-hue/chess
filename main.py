import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pywebpush import webpush, WebPushException
import json
app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# VAPID для Push-уведомлений
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
if not VAPID_PRIVATE_KEY:
    raise RuntimeError("VAPID_PRIVATE_KEY must be set in environment variables")

# Хранилище push-подписок (в памяти; в продакшене — в БД)
push_subscriptions = []
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
def send_push_notification(author: str, content: str):
    """Отправляет push всем подписанным устройствам"""
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
                vapid_claims={"sub": "mailto:admin@yourdomain.com"}
            )
        except WebPushException as e:
            print("Push failed:", e)
            if e.response and e.response.status_code == 410:
                push_subscriptions.remove(sub)
MESSAGES_URL = f"{SUPABASE_URL}/rest/v1/messages"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


async def icon192():
    return FileResponse("static/icon-192.png")

@app.get("/icon-512.png")
async def icon512():
    return FileResponse("static/icon-512.png")
@app.post("/subscribe")
async def subscribe(request: Request):
    subscription = await request.json()
    if subscription not in push_subscriptions:
        push_subscriptions.append(subscription)
    return JSONResponse({"status": "ok"})
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
            # Отправляем push-уведомление (работает даже при закрытой вкладке!)
send_push_notification(author, content)

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
