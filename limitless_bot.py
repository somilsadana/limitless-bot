from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timezone, timedelta
import re
import time
import requests
import os

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

MIN_DISTANCE_PERCENT = 4.0
PERFECT_DISTANCE_PERCENT = 10.0
USE_ABOVE_TARGET = False  # True = "YES" bets, False = "NO" bets
ALERT_WINDOW_MINUTES = 65  # 1 hour window
# =======================================================

class LimitlessBot:
    def __init__(self):
        self.price_cache = {}
        
    def setup_driver(self):
        """Setup browser for GitHub."""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.binary_location = '/usr/bin/chromium-browser'
        
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    
    def fetch_limitless_markets(self, driver):
        """Get all markets from Limitless."""
        print("📡 Fetching all markets from Limitless...")
        markets = []
        
        try:
            driver.get("https://limitless.exchange/pro/cat/daily")
            time.sleep(5)
            
            page_html = driver.page_source
            
            # Find all markets
            pattern = r'\$([A-Z]{2,5})\s+above\s+\$([\d,]+\.?\d*)\s+on\s+([A-Za-z]+\s+\d+,\s+\d{2}:\d{2}\s+UTC)[^%]*(\d+\.?\d*)%'
            matches = re.findall(pattern, page_html)
            
            print(f"✅ Found {len(matches)} markets")
            
            for match in matches:
                try:
                    asset = match[0]
                    target_price = float(match[1].replace(',', ''))
                    date_str = match[2]
                    probability = float(match[3])
                    
                    closing_time = self.parse_date(date_str)
                    
                    markets.append({
                        'asset': asset,
                        'target_price': target_price,
                        'closing_time_utc': closing_time,
                        'probability': probability,
                        'current_price': None,
                        'price_diff_percent': None,
                        'signal': "PENDING",
                        'bet_type': None,
                        'edge_score': 0,
                        'bet_quality': "NONE",
                        'reason': ""
                    })
                    
                except Exception as e:
                    print(f"❌ Error parsing {match[0]}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Fetch error: {e}")
        
        return markets
    
    def parse_date(self, date_str):
        """Convert date text to datetime."""
        current_utc = datetime.now(timezone.utc)
        try:
            date_str = date_str.replace(',', '')
            parsed_time = datetime.strptime(date_str, '%b %d %H:%M %Z')
            parsed_time = parsed_time.replace(year=current_utc.year, tzinfo=timezone.utc)
            
            if parsed_time < current_utc:
                parsed_time = parsed_time.replace(year=current_utc.year + 1)
            return parsed_time
        except Exception as e:
            print(f"Date parse error: {e}")
            return current_utc
    
    def fetch_current_price(self, asset):
        """Get live price from Binance."""
        try:
            symbol_map = {
                'BTC': 'BTCUSDT', 'ETH': 'ETHUSDT', 'BNB': 'BNBUSDT',
                'SOL': 'SOLUSDT', 'XRP': 'XRPUSDT', 'ADA': 'ADAUSDT',
                'AVAX': 'AVAXUSDT', 'DOGE': 'DOGEUSDT', 'LINK': 'LINKUSDT',
                'TRX': 'TRXUSDT', 'LTC': 'LTCUSDT', 'BCH': 'BCHUSDT',
                'XLM': 'XLMUSDT', 'HBAR': 'HBARUSDT', 'SUI': 'SUIUSDT',
                'PAXG': 'PAXGUSDT', 'CYS': 'CYSUSDT'
            }
            
            symbol = symbol_map.get(asset)
            if not symbol:
                return None
            
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            response = requests.get(url, timeout=10)
            data = response.json()
            return float(data['price'])
            
        except Exception as e:
            print(f"⚠️  Price fetch failed for {asset}: {e}")
            return None
    
    def calculate_signal(self, current_price, target_price):
        """Apply the 4-10% rule."""
        price_diff = ((current_price - target_price) / target_price) * 100
        abs_diff = abs(price_diff)
        
        if USE_ABOVE_TARGET:
            # YES bets (price above target)
            if price_diff >= PERFECT_DISTANCE_PERCENT:
                return "PERFECT YES", "YES", price_diff, 100, "PERFECT"
            elif MIN_DISTANCE_PERCENT <= price_diff < PERFECT_DISTANCE_PERCENT:
                score = 60 + ((price_diff - MIN_DISTANCE_PERCENT) / 6) * 40
                return "STRONG YES", "YES", price_diff, int(score), "GOOD"
            elif 0 < price_diff < MIN_DISTANCE_PERCENT:
                return "NO BET", None, price_diff, 0, "NONE"
            else:
                return "AVOID", None, price_diff, 0, "NONE"
        else:
            # NO bets (price below target)
            if price_diff <= -PERFECT_DISTANCE_PERCENT:
                return "PERFECT NO", "NO", price_diff, 100, "PERFECT"
            elif -PERFECT_DISTANCE_PERCENT < price_diff <= -MIN_DISTANCE_PERCENT:
                score = 60 + ((abs_diff - MIN_DISTANCE_PERCENT) / 6) * 40
                return "STRONG NO", "NO", price_diff, int(score), "GOOD"
            elif -MIN_DISTANCE_PERCENT < price_diff < 0:
                return "NO BET", None, price_diff, 0, "NONE"
            else:
                return "AVOID", None, price_diff, 0, "NONE"
    
    def analyze_markets(self, markets):
        """Analyze all markets."""
        print(f"\n📊 Analyzing {len(markets)} markets...")
        
        for market in markets:
            if market['closing_time_utc'] < datetime.now(timezone.utc):
                market['signal'] = "CLOSED"
                continue
            
            current_price = self.fetch_current_price(market['asset'])
            if not current_price:
                market['signal'] = "PRICE FETCH FAILED"
                continue
            
            market['current_price'] = current_price
            
            signal, bet_type, price_diff, score, quality = self.calculate_signal(
                current_price, market['target_price']
            )
            
            market.update({
                'price_diff_percent': price_diff,
                'signal': signal,
                'bet_type': bet_type,
                'edge_score': score,
                'bet_quality': quality
            })
        
        return markets
    
    def send_telegram_alert(self, market, minutes_left):
        """Send individual alert for each market."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return False
        
        try:
            # Choose emoji based on signal
            emoji = "🎯" if market['bet_quality'] == 'PERFECT' else \
                    "✅" if market['bet_quality'] == 'GOOD' else \
                    "➖" if market['signal'] == 'NO BET' else \
                    "⛔" if market['signal'] == 'AVOID' else "❓"
            
            # Get price difference with sign
            diff_sign = "+" if market['price_diff_percent'] > 0 else ""
            
            message = (
                f"{emoji} **{market['asset']}**\n"
                f"📡 Signal: {market['signal']}\n"
                f"🎯 Bet Type: {market['bet_type'] or 'NONE'}\n"
                f"💰 Target: ${market['target_price']:.6f}\n"
                f"📈 Current: ${market['current_price']:.6f}\n"
                f"📊 Difference: {diff_sign}{market['price_diff_percent']:.2f}%\n"
                f"⭐ Score: {market['edge_score']}/100\n"
                f"📋 Market Prob: {market['probability']}%\n"
                f"⏰ Closes in: {minutes_left} minutes\n"
                f"🕐 Close Time: {market['closing_time_utc'].strftime('%H:%M UTC')}"
            )
            
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            print(f"Telegram error for {market['asset']}: {e}")
            return False
    
    def run(self):
        """Main function - 2-hour scans with all alerts."""
        print("=" * 70)
        print("LIMITLESS BOT - 2-HOUR SCANS")
        print("ALERTS FOR ALL MARKETS")
        print("=" * 70)
        
        driver = self.setup_driver()
        alerts_sent = 0
        
        try:
            # 1. Fetch markets
            markets = self.fetch_limitless_markets(driver)
            
            # 2. Analyze
            markets = self.analyze_markets(markets)
            
            # 3. Send alerts for ALL markets closing in 1 hour
            now = datetime.now(timezone.utc)
            print(f"\n📱 Sending Telegram alerts for markets closing in {ALERT_WINDOW_MINUTES} minutes...")
            
            for market in markets:
                if market.get('current_price'):
                    minutes_left = (market['closing_time_utc'] - now).total_seconds() / 60
                    
                    # Only alert for markets closing in our window
                    if 0 < minutes_left <= ALERT_WINDOW_MINUTES:
                        if self.send_telegram_alert(market, int(minutes_left)):
                            print(f"   ✅ {market['asset']}: {market['signal']} ({market['price_diff_percent']:+.2f}%)")
                            alerts_sent += 1
                            time.sleep(0.5)  # Small delay between messages
            
            # 4. Summary
            perfect = len([m for m in markets if m['bet_quality'] == 'PERFECT'])
            good = len([m for m in markets if m['bet_quality'] == 'GOOD'])
            no_bet = len([m for m in markets if m['signal'] == 'NO BET'])
            avoid = len([m for m in markets if m['signal'] == 'AVOID'])
            
            print(f"\n{'='*70}")
            print("📊 2-HOUR SCAN COMPLETE")
            print(f"   Scan Time: {now.strftime('%H:%M UTC')}")
            print(f"   Total Markets: {len(markets)}")
            print(f"   🎯 Perfect bets: {perfect}")
            print(f"   ✅ Good bets: {good}")
            print(f"   ➖ No bets: {no_bet}")
            print(f"   ⛔ Avoid: {avoid}")
            print(f"   📱 Alerts sent: {alerts_sent}")
            
            # Next 2-hour scan
            next_scan = now + timedelta(hours=2)
            print(f"   ⏰ Next scan: {next_scan.strftime('%H:%M UTC')}")
            print(f"{'='*70}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            try:
                driver.quit()
            except:
                pass

# Run the bot
if __name__ == "__main__":
    bot = LimitlessBot()
    bot.run()
