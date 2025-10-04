from datetime import datetime
from fastapi import Response
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import httpx
from pywebpush import webpush, WebPushException
import json
import importlib.util

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
    "Prefer": "return=representation"  # чтобы получить ответ после POST
}

# === Система ботов ===
bot_response = None

def load_bot():
    """Загружает бота из папки /bot/bot.py"""
    global bot_response
    try:
        bot_path = "bot/bot.py"
        if not os.path.exists(bot_path):
            print("❌ Файл бота не найден")
            return None
        
        # Динамическая загрузка модуля
        spec = importlib.util.spec_from_file_location("bot", bot_path)
        bot_module = importlib.util.module_from_spec(spec)
        
        def otvet(text):
            global bot_response
            bot_response = text
        
        # Добавляем функцию otvet в модуль
        bot_module.otvet = otvet
        
        spec.loader.exec_module(bot_module)
        print("✅ Бот загружен")
        return bot_module
        
    except Exception as e:
        print(f"❌ Ошибка загрузки бота: {e}")
        return None

# Загружаем бота при старте
bot_module = load_bot()

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
@app.delete("/subscribe")
async def unsubscribe(request: Request):
    try:
        subscription = await request.json()
        endpoint = subscription.get("endpoint")
        
        # Удаляем подписку из списка
        global push_subscriptions
        push_subscriptions = [sub for sub in push_subscriptions if sub.get("endpoint") != endpoint]
        
        print(f"Unsubscribed: {endpoint}")
        return JSONResponse({"status": "unsubscribed"})
        
    except Exception as e:
        print("Unsubscribe error:", e)
        return JSONResponse({"status": "error"}, status_code=400)

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

@app.head("/")
async def head_root():
    """Обработка HEAD запросов для UptimeRobot"""
    return Response()

@app.get("/health")
async def health_check():
    """Эндпоинт для проверки здоровья сервера"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.head("/health")
async def head_health():
    """HEAD для health check"""
    return Response()

# === WebSocket ===

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)

    # Загрузка истории
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

            # === ОБРАБОТКА КОМАНД БОТА ===
            global bot_response
            bot_response = None
            
            if bot_module and content.startswith('/'):
                command = content.strip()
                
                # Ищем функцию обработчика команды
                for attr_name in dir(bot_module):
                    if attr_name.startswith('comandOtvet-') and command in attr_name:
                        try:
                            # Вызываем функцию бота
                            func = getattr(bot_module, attr_name)
                            func()
                            
                            # Если бот ответил - отправляем ответ
                            if bot_response:
                                bot_msg = f'<b>🤖 Бот</b>: {bot_response}'
                                
                                # Отправляем ответ в чат
                                for conn in connections[:]:
                                    try:
                                        await conn.send_text(bot_msg)
                                    except:
                                        if conn in connections:
                                            connections.remove(conn)
                                
                                # Сохраняем в базу
                                async with httpx.AsyncClient(timeout=10.0) as client:
                                    await client.post(
                                        MESSAGES_URL,
                                        headers=headers,
                                        json={
                                            "author": "🤖 Бот", 
                                            "content": bot_response,
                                            "notified": True
                                        }
                                    )
                                
                                bot_response = None
                                continue  # Пропускаем обычную обработку
                                
                        except Exception as e:
                            print(f"❌ Ошибка выполнения команды {command}: {e}")

            msg_id = None
            # 1. Сохраняем сообщение с notified=false
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        MESSAGES_URL,
                        headers=headers,
                        json={"author": author, "content": content, "notified": False}
                    )
                    if resp.status_code == 201:
                        created = resp.json()
                        if created and isinstance(created, list):
                            msg_id = created[0].get("id")
            except Exception as e:
                print("Save error:", e)

            # 2. Рассылаем по WebSocket
            full_msg = f'<b>{author}</b>: {content}'
            for conn in connections[:]:
                try:
                    await conn.send_text(full_msg)
                except:
                    if conn in connections:
                        connections.remove(conn)

            # 3. Отправляем push ТОЛЬКО если сообщение новое и ещё не уведомляли
            if msg_id is not None:
                try:
                    # Проверим, не уведомляли ли уже (на всякий случай)
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        check = await client.get(
                            f"{MESSAGES_URL}?id=eq.{msg_id}&select=notified",
                            headers=headers
                        )
                        if check.status_code == 200 and check.json():
                            notified = check.json()[0].get("notified", True)
                            if not notified:
                                send_push_notification(author, content)
                                # Обновляем notified = true
                                await client.patch(
                                    f"{MESSAGES_URL}?id=eq.{msg_id}",
                                    headers={**headers, "Prefer": "return=minimal"},
                                    json={"notified": True}
                                )
                except Exception as e:
                    print("Notify/update error:", e)

    except WebSocketDisconnect:
        if websocket in connections:
            connections.remove(websocket)
