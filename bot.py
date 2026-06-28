#!/usr/bin/env python3
import os, json, logging, asyncio, time
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(format="%(asctime)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8959012165:AAEtoZshlEIaK1r_uXuT2WkuCouWiX7RsTw")
STREAM_API_KEY = os.environ.get("STREAM_API_KEY", "roSeR9B68ZQb3iSXnx0qNXJ5xjLO3kfY")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://kcgxjw54o6ji2.kimi.page")
TON_ADDRESS = "UQDH-WYTxfXLX_tczh-GXVdBMDld7bZH7S_tAlgonOUNGCCT"
pending_orders = {}

async def api_request(action, **params):
    payload = {"key": STREAM_API_KEY, "action": action, **params}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("https://stream-promotion.ru/api/v2", data=payload, timeout=30) as resp:
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}

async def start(update, context):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Открыть AdForce", web_app=WebAppInfo(url=MINI_APP_URL))],
    ])
    await update.message.reply_text(
        "👋 *AdForce Bot*\\n🚀 Продвижение в соцсетях\\n💎 Оплата: USDT (сеть TON)\\n\\nНажмите кнопку ниже 👇",
        parse_mode="Markdown", reply_markup=kb,
    )

async def balance(update, context):
    r = await api_request("balance")
    await update.message.reply_text(f"💰 Баланс: *{r.get('balance', '?')}* руб.", parse_mode="Markdown")

async def web_app(update, context):
    data_str = update.effective_message.web_app_data.data
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    try:
        data = json.loads(data_str)
    except:
        return await update.message.reply_text("❌ Ошибка данных")
    
    if data.get("action") != "create_invoice":
        return
    
    amount = data.get("amount", 0)
    rub_total = data.get("rubTotal", 0)
    items = data.get("items", [])
    link = data.get("link", "")
    order_ref = f"AF{user.id}_{int(time.time())}"
    
    pending_orders[order_ref] = {
        "chat_id": chat_id, "amount": amount, "rub_total": rub_total,
        "items": items, "link": link, "status": "pending", "created_at": time.time(),
    }
    
    items_text = "\n".join(f"  • {i.get('name', 'Услуга')} x{i.get('qty', 1)}" for i in items)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Оплатить через @wallet", url=f"https://t.me/wallet?startattach=pay_{order_ref}")],
        [InlineKeyboardButton("📋 Адрес TON", callback_data=f"addr:{order_ref}")],
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check:{order_ref}")],
        [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel:{order_ref}")],
    ])
    
    await update.message.reply_text(
        f"📦 *Заказ #{order_ref}*\\n\\n🛒 Услуги:\\n{items_text}\\n\\n"
        f"💵 Сумма: {rub_total:.0f} руб.\\n"
        f"💰 К оплате: *{amount:.2f} USDT* (сеть TON)\\n\\n"
        f"Адрес: `{TON_ADDRESS}`\\n\\n"
        f"1. Отправьте USDT через @wallet\\n"
        f"2. Нажмите ✅ Я оплатил",
        parse_mode="Markdown", reply_markup=kb,
    )

async def callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("addr:"):
        ref = data.split(":", 1)[1]
        order = pending_orders.get(ref)
        if not order: return await query.edit_message_text("❌ Заказ не найден.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check:{ref}")],
        ])
        await query.edit_message_text(
            f"💎 *Адрес для оплаты*\\n\\nСумма: *{order['amount']:.2f} USDT*\\n\\n"
            f"`{TON_ADDRESS}`\\n\\n"
            f"⚠️ Только USDT в сети TON!\\n"
            f"⚠️ Не с бирж под санкциями!",
            parse_mode="Markdown", reply_markup=kb,
        )
    
    elif data.startswith("check:"):
        ref = data.split(":", 1)[1]
        order = pending_orders.get(ref)
        if not order: return await query.edit_message_text("❌ Заказ не найден.")
        if order["status"] == "paid": return await query.edit_message_text("✅ Уже оплачен!")
        
        elapsed = time.time() - order["created_at"]
        if elapsed > 1800:
            return await query.edit_message_text("⏰ Время истекло. Создайте новый заказ.")
        
        amount = order["amount"]
        await query.edit_message_text(f"⏳ *Проверяем #{ref}...*\\nИщем {amount:.2f} USDT в блокчейне TON...\\n\\n_Это займет 10-20 секунд_", parse_mode="Markdown")
        
        result = await check_ton(amount)
        
        if result["found"]:
            order["status"] = "paid"
            await context.bot.send_message(chat_id=order["chat_id"],
                text=f"✅ *Оплата ПОДТВЕРЖДЕНА!*\\n\\n📦 #{ref}\\n💰 {result['amount']:.2f} USDT\\n🚀 *Отправляем в работу...*",
                parse_mode="Markdown",
            )
            await send_orders(context, ref, order)
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check:{ref}")],
                [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel:{ref}")],
            ])
            await context.bot.send_message(chat_id=order["chat_id"],
                text=f"❌ *Оплата НЕ НАЙДЕНА*\\n\\n"
                     f"📦 #{ref}\\n💰 Ожидалось: {amount:.2f} USDT\\n\\n"
                     f"Причина: {result.get('reason', 'неизвестно')}\\n\\n"
                     f"Возможные причины:\\n"
                     f"• Перевод еще не подтвержден (подождите 5-10 мин)\\n"
                     f"• Отправили не USDT или не в сети TON\\n"
                     f"• Сумма отличается\\n\\n"
                     f"⚠️ Попытка обмана приведет к блокировке!",
                parse_mode="Markdown", reply_markup=kb,
            )
    
    elif data.startswith("cancel:"):
        ref = data.split(":", 1)[1]
        order = pending_orders.pop(ref, None)
        if order and order.get("status") == "paid":
            await query.edit_message_text("❌ Уже оплачен. Нельзя отменить.")
        else:
            await query.edit_message_text("❌ Заказ отменен.")

async def check_ton(expected_amount):
    try:
        url = f"https://tonapi.io/v2/accounts/{TON_ADDRESS}/jettons/history"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"limit": 30}, timeout=15) as resp:
                if resp.status != 200:
                    return {"found": False, "reason": f"API error {resp.status}"}
                data = await resp.json()
                txs = data.get("history", [])
                if not txs:
                    return {"found": False, "reason": "нет транзакций"}
                
                now = time.time()
                for tx in txs:
                    if tx.get("action") != "JettonTransfer":
                        continue
                    receiver = tx.get("receiver", {}).get("address", "")
                    if TON_ADDRESS not in receiver:
                        continue
                    jetton = tx.get("jetton", {})
                    amount_raw = tx.get("amount", "0")
                    decimals = int(jetton.get("decimals", 6))
                    amount = int(amount_raw) / (10 ** decimals)
                    tx_time = tx.get("utime", 0)
                    if now - tx_time > 1800:
                        continue
                    if amount >= expected_amount * 0.9:
                        return {"found": True, "amount": amount, "tx_hash": tx.get("hash", "?")[:15]}
                return {"found": False, "reason": "нет входящих USDT на нужную сумму"}
    except Exception as e:
        return {"found": False, "reason": f"ошибка: {str(e)[:100]}"}

async def send_orders(context, ref, order):
    items = order.get("items", [])
    results = []
    for item in items:
        result = await api_request("add", service=item.get("service"), quantity=item.get("qty", 1), link=order.get("link", ""))
        results.append(result)
        await asyncio.sleep(0.5)
    success = sum(1 for r in results if "order" in r)
    lines = [f"✅ ID {r['order']}" if "order" in r else f"❌ {r.get('error', 'Error')}" for r in results]
    order["status"] = "completed" if success > 0 else "failed"
    await context.bot.send_message(chat_id=order["chat_id"],
        text=f"📊 *Результат #{ref}*\\nУспешно: *{success}*\\n\\n" + "\n".join(lines),
        parse_mode="Markdown",
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app))
    app.add_handler(CallbackQueryHandler(callback))
    logger.info("=== BOT STARTED ===")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
