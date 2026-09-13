import os
import requests
import ccxt
import pandas as pd
import ta

# --- CONFIGURATION TELEGRAM ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    """Envoie une alerte sur Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Erreur: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID absents des Secrets GitHub.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erreur d'envoi Telegram : {e}")

def run_scanner():
    # Connexion à OKX
    exchange = ccxt.okx({'enableRateLimit': True})
    
    # Chargement des marchés disponibles
    markets = exchange.load_markets()
    usdt_pairs = [
        symbol for symbol, market in markets.items()
        if market['quote'] == 'USDT' and market.get('spot', False) and market.get('active', True)
    ]
    
    # Sélection des 60 paires USDT avec le plus gros volume
    tickers = exchange.fetch_tickers(usdt_pairs)
    sorted_pairs = sorted(
        tickers.items(), 
        key=lambda x: x[1]['quoteVolume'] if x[1] and x[1].get('quoteVolume') else 0, 
        reverse=True
    )
    top_pairs = [item[0] for item in sorted_pairs[:60]]
    
    alerts = []

    for symbol in top_pairs:
        try:
            # Récupération des bougies de 1 heure
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
            if not ohlcv or len(ohlcv) < 200:
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # --- CALCULS DES INDICATEURS ---
            df['rsi'] = ta.momentum.rsi(df['close'], window=14)
            df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)
            df['vol_sma'] = df['volume'].rolling(window=20).mean()

            last_rsi = df['rsi'].iloc[-1]
            last_price = df['close'].iloc[-1]
            last_ema = df['ema200'].iloc[-1]
            last_vol = df['volume'].iloc[-1]
            avg_vol = df['vol_sma'].iloc[-1]

            if pd.isna(last_rsi) or pd.isna(last_ema):
                continue

            vol_text = "🔥 Très fort" if last_vol > (avg_vol * 1.5) else ("📈 Bon" if last_vol > avg_vol else "⚪ Calme")

            # Lien direct TradingView ciblant OKX
            clean_symbol = symbol.replace('/', '')
            tv_link = f"https://www.tradingview.com/chart/?symbol=OKX:{clean_symbol}"

            # --- DÉTECTION DES DIVERGENCES ---
            
            # SIGNAL D'ACHAT (Surchauffe baissière / Rebond potentiel)
            if last_rsi <= 35 and last_price > last_ema:
                stop_loss = last_price * 0.98
                take_profit = last_price * 1.04

                alerts.append(
                    f"🟢 **OPPORTUNITÉ D'ACHAT** : [{symbol}]({tv_link})\n"
                    f"• **Prix actuel** : `{last_price}` USDT\n"
                    f"• **Niveau d'aubaine (RSI)** : `{last_rsi:.1f}/100` (Très bas)\n"
                    f"• **Tendance globale** : 🟢 Haussière (au-dessus EMA 200)\n"
                    f"• **Activité des acheteurs** : {vol_text}\n"
                    f"-----------------------------\n"
                    f"🎯 **Plan de Trade suggéré :**\n"
                    f"  👉 **Acheter à** : `{last_price}`\n"
                    f"  🛡️ **Sécurité (Stop-Loss -2%)** : `{stop_loss:.4f}`\n"
                    f"  💰 **Objectif gain (Take-Profit +4%)** : `{take_profit:.4f}`"
                )

            # SIGNAL DE VENTE / CORRECTION
            elif last_rsi >= 65 and last_price < last_ema:
                stop_loss = last_price * 1.02
                take_profit = last_price * 0.96

                alerts.append(
                    f"🔴 **SIGNAL DE VENTE / RETRAIT** : [{symbol}]({tv_link})\n"
                    f"• **Prix actuel** : `{last_price}` USDT\n"
                    f"• **Niveau de surchauffe (RSI)** : `{last_rsi:.1f}/100` (Très haut)\n"
                    f"• **Tendance globale** : 🔴 Baissière (sous EMA 200)\n"
                    f"• **Activité des vendeurs** : {vol_text}\n"
                    f"-----------------------------\n"
                    f"🎯 **Plan suggéré :**\n"
                    f"  👉 **Prix d'alerte** : `{last_price}`\n"
                    f"  🛡️ **Protection (Stop-Loss +2%)** : `{stop_loss:.4f}`\n"
                    f"  💰 **Objectif baisse (Take-Profit -4%)** : `{take_profit:.4f}`"
                )

        except Exception as e:
            print(f"Erreur d'analyse sur {symbol}: {e}")
            continue

    # Envoi du bilan sur Telegram
    if alerts:
        header = f"🚨 **ALERTES OKX - DÉTECTION EN COURS** 🚨\n\n"
        full_message = header + "\n\n=============================\n\n".join(alerts)
        send_telegram_alert(full_message)
        print(f"{len(alerts)} alerte(s) envoyée(s) sur Telegram.")
    else:
        print("Scan OKX terminé : Le marché est calme, aucune opportunité détectée.")

if __name__ == "__main__":
    run_scanner()
