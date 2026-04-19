import os
import threading
import time
import requests
from datetime import datetime
import pytz
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import re

app = Flask(__name__)

# CORS configuration
ALLOWED_ORIGIN = os.environ.get('FRONTEND_URL', 'https://nowiba1.github.io')
CORS(app, origins=[ALLOWED_ORIGIN], supports_credentials=False)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', 'https://nowiba1.github.io')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

@app.route('/health', methods=['OPTIONS'])
@app.route('/api/formats', methods=['OPTIONS'])
@app.route('/api/download', methods=['OPTIONS'])
def handle_options():
    return '', 200

def should_be_awake():
    now = datetime.now(pytz.UTC)
    current_hour = now.hour
    return not (0 <= current_hour < 7)

def keep_alive():
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://youtube-4y2j.onrender.com')
    while True:
        if should_be_awake():
            try:
                requests.get(f"{app_url}/health", timeout=5)
                print(f"✓ Keep-alive ping at {datetime.now()}")
            except:
                pass
            time.sleep(840)
        else:
            print(f"💤 Sleep hours (00:00-07:00 UTC)")
            time.sleep(3600)

threading.Thread(target=keep_alive, daemon=True).start()

@app.route('/')
def index():
    return jsonify({"status": "active", "frontend": "https://nowiba1.github.io/youtube/"})

@app.route('/health')
def health():
    return jsonify({"status": "awake", "time": str(datetime.now())})

def get_yt_dlp_opts():
    """Return yt-dlp options that bypass bot detection"""
    return {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        # Use iOS client - weakest bot detection
        'extractor_args': {
            'youtube': {
                'player_client': ['ios'],
                'skip': ['webpage']
            }
        },
        # iOS user agent
        'user_agent': 'com.google.ios.youtube/19.49.7 (iPhone16,2; U; CPU iOS 18_2 like Mac OS X)',
        # No cookies needed
        'cookiefile': None,
    }

@app.route('/api/formats', methods=['POST'])
def get_formats():
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        print(f"Fetching formats for: {url}")
        
        ydl_opts = get_yt_dlp_opts()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('height') and f.get('ext') == 'mp4':
                    formats.append({
                        'format_id': f['format_id'],
                        'quality': f"{f['height']}p",
                        'ext': f['ext'],
                        'filesize': f.get('filesize', 0)
                    })
            
            seen = set()
            unique_formats = []
            for fmt in formats:
                if fmt['quality'] not in seen:
                    seen.add(fmt['quality'])
                    unique_formats.append(fmt)
            
            print(f"Found {len(unique_formats)} formats")
            
            return jsonify({
                "title": info.get('title', 'Unknown'),
                "thumbnail": info.get('thumbnail', ''),
                "video_formats": unique_formats
            })
            
    except Exception as e:
        print(f"ERROR in get_formats: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    temp_file = None
    temp_path = None
    
    try:
        data = request.json
        url = data.get('url')
        download_type = data.get('type', 'video')
        quality = data.get('quality', '720p')
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        print(f"Downloading: {url} as {download_type} ({quality})")
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{download_type}')
        temp_path = temp_file.name
        temp_file.close()
        
        ydl_opts = get_yt_dlp_opts()
        ydl_opts['outtmpl'] = temp_path.replace('.audio', '') if download_type == 'audio' else temp_path
        
        if download_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality.replace('kbps', ''),
            }]
        else:
            height = quality.replace('p', '')
            ydl_opts['format'] = f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]'
            ydl_opts['merge_output_format'] = 'mp4'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if download_type == 'audio':
                if filename.endswith(('.webm', '.m4a', '.opus')):
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                elif not filename.endswith('.mp3'):
                    filename = filename + '.mp3'
            
            safe_title = re.sub(r'[^\w\-_\. ]', '', info.get('title', 'video'))[:100]
            download_name = f"{safe_title}.{download_type == 'video' and 'mp4' or 'mp3'}"
            
            print(f"Download complete: {download_name}")
            
            return send_file(
                filename,
                as_attachment=True,
                download_name=download_name,
                mimetype=download_type == 'video' and 'video/mp4' or 'audio/mpeg'
            )
            
    except Exception as e:
        print(f"ERROR in download_video: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        try:
            if 'filename' in locals() and os.path.exists(filename):
                os.unlink(filename)
        except:
            pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
