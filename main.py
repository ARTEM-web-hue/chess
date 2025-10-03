from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import chess
import asyncio

app = FastAPI()

# Хранилище
waiting_players = []
games = {}  # game_id: { 'white': ws, 'black': ws, 'board': Board }

# Отдаём index.html на корень
@app.get("/")
async def root():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    await websocket.accept()

    waiting_players.append(websocket)
    game_id = None
    color = None

    try:
        # Попытка найти пару
        if len(waiting_players) >= 2:
            p1 = waiting_players.pop(0)
            p2 = waiting_players.pop(0)
            board = chess.Board()
            game_id = id(board)
            games[game_id] = {"white": p1, "black": p2, "board": board}

            await p1.send_text("color:white")
            await p2.send_text("color:black")
            await send_fen(game_id)
        else:
            await websocket.send_text("status:waiting")

        # Ожидание назначения игры (если только что создана)
        if game_id is None:
            for gid, g in games.items():
                if g["white"] == websocket or g["black"] == websocket:
                    game_id = gid
                    color = chess.WHITE if g["white"] == websocket else chess.BLACK
                    break

        # Основной цикл
        while True:
            data = await websocket.receive_text()
            if game_id not in games:
                break

            if data == "resign":
                await game_over(game_id, "resign")
                break

            try:
                move = chess.Move.from_uci(data)
                board = games[game_id]["board"]
                if move in board.legal_moves:
                    board.push(move)
                    await send_fen(game_id)

                    if board.is_game_over():
                        res = "1/2-1/2"
                        if board.is_checkmate():
                            res = "0-1" if board.turn == chess.WHITE else "1-0"
                        await game_over(game_id, f"result:{res}")
            except Exception:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in waiting_players:
            waiting_players.remove(websocket)
        # Удалить игру, если игрок отключился
        to_remove = None
        for gid, g in games.items():
            if g["white"] == websocket or g["black"] == websocket:
                to_remove = gid
                break
        if to_remove:
            del games[to_remove]

async def send_fen(game_id):
    if game_id in games:
        fen = games[game_id]["board"].fen()
        await broadcast(game_id, f"fen:{fen}")

async def broadcast(game_id, msg):
    if game_id in games:
        g = games[game_id]
        for ws in [g["white"], g["black"]]:
            try:
                await ws.send_text(msg)
            except:
                pass

async def game_over(game_id, msg):
    if game_id in games:
        await broadcast(game_id, msg)
        del games[game_id]
