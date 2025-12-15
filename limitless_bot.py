import requests
import time
import json
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Optional
import logging

# ===================== CONFIGURATION =====================
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # Can be channel ID or group ID

# API Configuration
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"

# Market data with targets and closing times
MARKETS = [
    {"symbol": "CYS", "target": 0.2911, "close_time": "2023-12-15 12:00"},
    {"symbol": "HBAR", "target": 0.1230, "close_time": "2023-12-15 09:00"},
    {"symbol": "ETH", "target": 3112.28, "close_time": "2023-12-15 06:00"},
    {"symbol": "AVAX", "target": 12.9470, "close_time": "2023-12-15 18:00"},
    {"symbol": "TRX", "target": 0.2747, "close_time": "2023-12-15 08:00"},
    {"symbol": "DOGE", "target": 0.1343, "close_time": "2023-12-15 20:00"},
    {"symbol": "BNB", "target": 886.61, "close_time": "2023-12-15 16:00"},
    {"symbol": "ADA", "target": 0.4035, "close_time": "2023-12-15 12:00"},
    {"symbol": "PAXG", "target": 4322.85, "close_time": "2023-12-15 11:00"},
    {"symbol": "BTC", "target": 90037.39, "close_time": "2023-12-15 10:00"},
    {"symbol": "LINK", "target": 13.51, "close_time": "2023-12-16 02:00"},
    {"symbol": "XLM", "target": 0.2287, "close_time": "2023-12-15 22:00"},
    {"symbol": "SOL", "target": 131.64, "close_time": "2023-12-15 14:00"},
    {"symbol": "XRP", "target": 1.9925, "close_time": "2023-12-15 23:00"},
    {"symbol": "SUI", "target": 1.5695, "close_time": "2023-12-16 04:00"},
    {"symbol": "LTC", "target": 78.974, "close_time": "2023-12-16 00:00"},
    {"symbol": "BCH", "target": 570.36, "close_time": "2023-12-15 17:00"},
]

# Coingecko ID mapping (you need to adjust these to match actual IDs)
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOGE": "dogecoin",
    "LINK": "chainlink",
    "TRX": "tron",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "XLM": "stellar",
    "HBAR": "hedera-hashgraph",
    "SUI": "sui",
    "PAXG": "pax-gold",
    "CYS": "cyclos",  # This might need adjustment
}

# Analysis thresholds
PERFECT_THRESHOLD = 0.30  # 0.30% difference for perfect bet
GOOD_THRESHOLD = 0.50    # 0.50% difference for good bet
AVOID_THRESHOLD = 1.00   # 1.00% difference to avoid

# ===================== TELEGRAM FUNCTIONS =====================
def send_telegram_message(message: str):
    """Send message to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"✅ Telegram alert sent!")
            return True
        else:
            print(f"❌ Failed to send Telegram alert: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")
        return False

def format_market_signal(market_data: Dict, current_price: float, status: str, 
                         percentage_diff: float, closes_in_minutes: int) -> str:
    """Format market signal for Telegram"""
    
    # Status emojis
    status_emojis = {
        "PERFECT": "🎯",
        "GOOD": "✅", 
        "NO_BET": "➖",
        "AVOID": "⛔"
    }
    
    emoji = status_emojis.get(status, "📊")
    
    # Determine signal direction
    if current_price < market_data["target"]:
        direction = "BELOW"
        action = "BUY" if status in ["PERFECT", "GOOD"] else "WAIT"
    else:
        direction = "ABOVE"
        action = "SELL" if status in ["PERFECT", "GOOD"] else "WAIT"
    
    message = f"""
{emoji} <b>{market_data['symbol']} - {status}</b>
━━━━━━━━━━━━━━━━━━
💰 Current: ${current_price:,.4f}
🎯 Target: ${market_data['target']:,.4f}
📈 Difference: {percentage_diff:+.2f}%
📊 Direction: {direction}
⚡ Action: {action}

⏰ Closes in: {closes_in_minutes} minutes
🕒 Close Time: {market_data['close_time']} UTC
━━━━━━━━━━━━━━━━━━
"""
    
    # Add additional notes based on status
    if status == "PERFECT":
        message += "🔥 <b>PERFECT ENTRY POINT!</b>"
    elif status == "GOOD":
        message += "👍 <b>Good opportunity</b>"
    elif status == "NO_BET":
        message += "🤔 <b>Wait for better entry</b>"
    elif status == "AVOID":
        message += "⚠️ <b>Avoid this trade</b>"
    
    return message

# ===================== MARKET ANALYSIS =====================
def get_current_prices():
    """Fetch current prices from CoinGecko API"""
    ids = list(COINGECKO_IDS.values())
    ids_param = ",".join(ids)
    
    params = {
        "ids": ids_param,
        "vs_currencies": "usd"
    }
    
    try:
        response = requests.get(COINGECKO_API_URL, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            
            # Convert to symbol-based dictionary
            prices = {}
            for symbol, cg_id in COINGECKO_IDS.items():
                if cg_id in data and "usd" in data[cg_id]:
                    prices[symbol] = data[cg_id]["usd"]
                else:
                    prices[symbol] = 0.0
                    print(f"⚠️ Price not found for {symbol} ({cg_id})")
            
            return prices
        else:
            print(f"❌ API Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error fetching prices: {e}")
        return None

def analyze_market(market_data: Dict, current_price: float) -> Dict:
    """Analyze a single market and return analysis results"""
    
    if current_price == 0:
        return {
            "status": "ERROR",
            "percentage_diff": 0,
            "should_alert": False
        }
    
    # Calculate percentage difference
    target = market_data["target"]
    percentage_diff = ((current_price - target) / target) * 100
    
    # Determine status based on thresholds
    abs_diff = abs(percentage_diff)
    
    if abs_diff <= PERFECT_THRESHOLD:
        status = "PERFECT"
    elif abs_diff <= GOOD_THRESHOLD:
        status = "GOOD"
    elif abs_diff <= AVOID_THRESHOLD:
        status = "NO_BET"
    else:
        status = "AVOID"
    
    # Calculate closing time in minutes
    utc_now = datetime.now(pytz.utc)
    close_time_str = market_data["close_time"]
    
    # Parse close time (adjust format if needed)
    try:
        close_time = datetime.strptime(close_time_str, "%Y-%m-%d %H:%M")
        close_time = pytz.utc.localize(close_time)
        closes_in_minutes = int((close_time - utc_now).total_seconds() / 60)
    except:
        closes_in_minutes = 0
    
    # Always send alerts for all statuses
    should_alert = True
    
    return {
        "status": status,
        "percentage_diff": percentage_diff,
        "closes_in_minutes": closes_in_minutes,
        "should_alert": should_alert,
        "current_price": current_price
    }

def scan_all_markets():
    """Main scanning function"""
    print("=" * 70)
    print("LIMITLESS BOT - COMPREHENSIVE MARKET SCAN")
    print("ALERTS FOR ALL MARKET CONDITIONS")
    print("=" * 70)
    
    # Get current time
    utc_now = datetime.now(pytz.utc)
    print(f"\n📡 Scan started at: {utc_now.strftime('%H:%M UTC')}")
    
    # Fetch all prices
    print("\n📊 Fetching current prices from CoinGecko...")
    prices = get_current_prices()
    
    if not prices:
        print("❌ Failed to fetch prices")
        return
    
    print(f"✅ Successfully fetched {len(prices)} prices")
    
    # Analyze each market
    perfect_count = 0
    good_count = 0
    no_bet_count = 0
    avoid_count = 0
    alert_count = 0
    error_count = 0
    
    print("\n🔍 Analyzing all markets...")
    print("-" * 70)
    
    all_analyses = []
    
    for market in MARKETS:
        symbol = market["symbol"]
        current_price = prices.get(symbol, 0)
        
        if current_price == 0:
            error_count += 1
            print(f"❌ {symbol}: Price fetch failed")
            continue
        
        # Analyze market
        analysis = analyze_market(market, current_price)
        all_analyses.append((market, analysis))
        
        # Update counters
        status = analysis["status"]
        if status == "PERFECT":
            perfect_count += 1
        elif status == "GOOD":
            good_count += 1
        elif status == "NO_BET":
            no_bet_count += 1
        elif status == "AVOID":
            avoid_count += 1
        
        # Send Telegram alert for ALL statuses
        if analysis["should_alert"]:
            message = format_market_signal(
                market,
                analysis["current_price"],
                status,
                analysis["percentage_diff"],
                analysis["closes_in_minutes"]
            )
            
            if send_telegram_message(message):
                alert_count += 1
                print(f"📱 {symbol}: {status} alert sent!")
            else:
                print(f"❌ {symbol}: Failed to send alert")
        
        # Print to console
        print(f"{symbol:4s}: {status:8s} | ${current_price:12.6f} | {analysis['percentage_diff']:+.2f}% | "
              f"Closes in: {analysis['closes_in_minutes']} min")
    
    # Send summary
    print("\n" + "=" * 70)
    print("📊 COMPREHENSIVE SCAN COMPLETE")
    print("=" * 70)
    
    summary = f"""
📊 SCAN SUMMARY
━━━━━━━━━━━━━━━━━━
🕒 Scan Time: {utc_now.strftime('%H:%M UTC')}
📈 Total Markets: {len(MARKETS)}
━━━━━━━━━━━━━━━━━━
🎯 Perfect bets: {perfect_count}
✅ Good bets: {good_count}
➖ No bets: {no_bet_count}
⛔ Avoid: {avoid_count}
❌ Errors: {error_count}
━━━━━━━━━━━━━━━━━━
📱 Alerts sent: {alert_count}
⏰ Next scan: {(utc_now + timedelta(hours=2)).strftime('%H:%M UTC')}
━━━━━━━━━━━━━━━━━━
"""
    
    print(summary)
    send_telegram_message(summary)
    
    # Detailed analysis table
    detail_msg = "📈 <b>DETAILED MARKET ANALYSIS</b>\n"
    detail_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for market, analysis in sorted(all_analyses, key=lambda x: x[0]['symbol']):
        symbol = market['symbol']
        status = analysis['status']
        price = analysis['current_price']
        diff = analysis['percentage_diff']
        
        status_emoji = {
            "PERFECT": "🎯",
            "GOOD": "✅",
            "NO_BET": "➖",
            "AVOID": "⛔"
        }.get(status, "📊")
        
        detail_msg += f"{status_emoji} <code>{symbol:4s}</code>: {status:8s} | ${price:12.4f} | {diff:+.2f}%\n"
    
    send_telegram_message(detail_msg)

# ===================== MAIN EXECUTION =====================
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Starting Limitless Trading Bot...")
    print("⚡ Sending alerts for ALL market conditions")
    print(f"📱 Telegram notifications enabled for chat: {TELEGRAM_CHAT_ID}")
    
    try:
        # Run the scan
        scan_all_markets()
        
        print("\n✅ Scan completed successfully!")
        print("📱 Check your Telegram for detailed alerts")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
