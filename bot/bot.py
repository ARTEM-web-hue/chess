import requests
import json

def get_lichess_ratings(username):
    try:
        # Получаем данные пользователя
        response = requests.get(f"https://lichess.org/api/user/{username}")
        response.raise_for_status()
        data = response.json()
        
        # Извлекаем рейтинги
        perfs = data.get("perfs", {})
        
        # Текущие рейтинги
        ultra_bullet = perfs.get("ultraBullet", {}).get("rating", "N/A")
        bullet = perfs.get("bullet", {}).get("rating", "N/A")
        
        # Рекорды
        ultra_bullet_best = perfs.get("ultraBullet", {}).get("best", "N/A")
        bullet_best = perfs.get("bullet", {}).get("best", "N/A")
        
        # Форматируем результат
        resa = f"""ультрапуля: {ultra_bullet}
пуля: {bullet}
рекорд по ультрапуле: {ultra_bullet_best}
рекорд по пуле: {bullet_best}"""
        
        return resa
        
    except requests.exceptions.RequestException as e:
        return f"Ошибка: {e}"

# Использование
resa = get_lichess_ratings("atemmax")
print(resa)
def comandOtvet-/Погода():
  pog="26 градусов цельсия наверно уж"
  otvet(f"{pog}")
def comandOtvet-/help():
  otvet("Команды: /pog")
def comandOtvet-/atemmax():
  otvet(f"{resa}")
