import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import time

# === НАСТРОЙКИ ===
TELEGRAM_BOT_TOKEN = '8454639973:AAGUwELfoMRgDiCSXfmpWdj68jyP7_1NZPk'
CHANNEL_USERNAME = '@rusl_pay'
TON_ADDRESS = 'UQB20fJp5OMeLtsXmf4OxrnobADEoYxBjDQfI5fROEgS1Fcl'
DISPLAY_NAME = 'meow.ton'

# === ПОРОГИ СУММ ===
MIN_INCOMING_AMOUNT = 0.5    # Входящие от 0.5 TON
MIN_OUTGOING_AMOUNT = 5.0    # Исходящие от 5 TON

bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def get_transactions(address):
    url = f"https://tonapi.io/v2/blockchain/accounts/{address}/transactions"
    params = {'limit': 15}
    
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    
    async with aiohttp.ClientSession() as session:
        try:
            await asyncio.sleep(1.5)
            async with session.get(url, params=params, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('transactions', [])
                elif resp.status == 429:
                    print("⏳ Лимит запросов, ждем...")
                    await asyncio.sleep(30)
                    return []
                else:
                    return []
        except Exception as e:
            print(f"Ошибка API: {e}")
            return []

def check_transaction_amount(tx):
    """Проверяет, проходит ли транзакция по порогам суммы"""
    try:
        msgs = tx.get('msgs', [])
        
        if msgs:
            for msg in msgs:
                msg_type = msg.get('msg_type', '')
                value = msg.get('value', 0) / 1e9
                
                # Входящая транзакция
                if msg_type == 'ext_in' and msg.get('source'):
                    return value >= MIN_INCOMING_AMOUNT, value, "incoming"
                
                # Исходящая транзакция
                elif msg_type == 'ext_out' and msg.get('destination'):
                    return value >= MIN_OUTGOING_AMOUNT, value, "outgoing"
        
        return False, 0, "unknown"
    except:
        return False, 0, "unknown"

def format_transaction_message(tx, display_name, full_address):
    try:
        tx_hash = tx.get('hash', 'unknown')
        tx_hash_short = tx_hash[:6] + '...' + tx_hash[-6:]
        
        timestamp = tx.get('utime', time.time())
        time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        amount = 0
        direction = "🔄 Транзакция"
        from_addr = "неизвестно"
        to_addr = "неизвестно"
        
        msgs = tx.get('msgs', [])
        
        if msgs:
            for msg in msgs:
                msg_type = msg.get('msg_type', '')
                value = msg.get('value', 0) / 1e9
                
                if msg_type == 'ext_in' and msg.get('source'):
                    direction = "⬇️ ВХОДЯЩЕЕ"
                    amount = value
                    from_addr = msg.get('source', 'неизвестно')
                    to_addr = display_name
                    
                    if len(from_addr) > 10:
                        from_addr = from_addr[:6] + '...' + from_addr[-6:]
                    break
                
                elif msg_type == 'ext_out' and msg.get('destination'):
                    direction = "⬆️ ИСХОДЯЩЕЕ"
                    amount = value
                    from_addr = display_name
                    to_addr = msg.get('destination', 'неизвестно')
                    
                    if len(to_addr) > 10:
                        to_addr = to_addr[:6] + '...' + to_addr[-6:]
                    break
        
        tx_link = f"https://tonviewer.com/transaction/{tx_hash}"
        
        # Добавляем информацию о порогах в сообщение
        if direction == "⬇️ ВХОДЯЩЕЕ":
            threshold_info = f"(порог: {MIN_INCOMING_AMOUNT} TON)"
        else:
            threshold_info = f"(порог: {MIN_OUTGOING_AMOUNT} TON)"
        
        message = (
            f"🔔 **{direction}** на {display_name}\n"
            f"⏰ Время: {time_str}\n"
            f"💰 Сумма: **{amount:.3f} TON** {threshold_info}\n"
            f"📤 От: `{from_addr}`\n"
            f"📥 Кому: `{to_addr}`\n"
            f"🔗 [Посмотреть транзакцию]({tx_link})"
        )
        
        return message
        
    except Exception as e:
        print(f"Ошибка форматирования: {e}")
        return f"🔔 Новая транзакция на {display_name}\nХэш: {tx.get('hash', 'unknown')}"

async def monitor():
    print(f"🚀 Мониторинг кошелька: {DISPLAY_NAME}")
    print(f"📢 Канал: {CHANNEL_USERNAME}")
    print(f"💰 Пороги: входящие ≥ {MIN_INCOMING_AMOUNT} TON, исходящие ≥ {MIN_OUTGOING_AMOUNT} TON")
    print(f"🔗 https://tonviewer.com/{TON_ADDRESS}")
    print("-" * 60)
    
    known_hashes = set()
    error_count = 0
    
    while True:
        try:
            txs = await get_transactions(TON_ADDRESS)
            
            if txs and len(txs) > 0:
                error_count = 0
                new_txs = []
                
                for tx in txs:
                    tx_hash = tx.get('hash', '')
                    if tx_hash and tx_hash not in known_hashes:
                        # Проверяем сумму перед добавлением
                        is_valid, amount, tx_type = check_transaction_amount(tx)
                        
                        if is_valid:
                            new_txs.append(tx)
                            print(f"✅ Подходит: {tx_type}, сумма: {amount:.3f} TON")
                        else:
                            if amount > 0:
                                print(f"⏭️ Пропущено ({tx_type}): {amount:.3f} TON (ниже порога)")
                        
                        known_hashes.add(tx_hash)
                
                if len(known_hashes) > 200:
                    known_hashes = set(list(known_hashes)[-100:])
                
                if new_txs:
                    print(f"\n🆕 Найдено {len(new_txs)} новых транзакций (соответствуют порогам)!")
                    
                    for tx in new_txs:
                        msg = format_transaction_message(tx, DISPLAY_NAME, TON_ADDRESS)
                        
                        try:
                            await bot.send_message(
                                chat_id=CHANNEL_USERNAME, 
                                text=msg,
                                parse_mode='Markdown',
                                disable_web_page_preview=True
                            )
                            
                            tx_hash = tx.get('hash', 'unknown')
                            print(f"✅ Отправлена: {tx_hash[:8]}...")
                            print(f"   Ссылка: https://tonviewer.com/transaction/{tx_hash}")
                            
                        except TelegramError as e:
                            print(f"❌ Ошибка отправки: {e}")
                            try:
                                msg_plain = msg.replace('**', '').replace('`', '')
                                await bot.send_message(
                                    chat_id=CHANNEL_USERNAME, 
                                    text=msg_plain,
                                    disable_web_page_preview=True
                                )
                                print(f"✅ Отправлена (без форматирования)")
                            except:
                                pass
                        
                        await asyncio.sleep(1)
            else:
                error_count += 1
                if error_count % 10 == 0:
                    print(f"⏳ Мониторинг... (проверок: {error_count})")
            
        except Exception as e:
            print(f"❌ Ошибка мониторинга: {e}")
            error_count += 1
        
        await asyncio.sleep(20)

async def main():
    try:
        me = await bot.get_me()
        print(f"✅ Бот @{me.username} запущен")
        print(f"✅ Бот является админом в канале {CHANNEL_USERNAME}")
        print("-" * 60)
    except Exception as e:
        print(f"❌ Ошибка подключения к Telegram: {e}")
        return
    
    await monitor()

if __name__ == '__main__':
    asyncio.run(main())
