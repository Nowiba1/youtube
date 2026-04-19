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

@app.route('/api/formats', methods=['POST'])
def get_formats():
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'extractor_args': {'youtube': {'player_client': ['android']}},
        }
        
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
            
            return jsonify({
                "title": info.get('title', 'Unknown'),
                "thumbnail": info.get('thumbnail', ''),
                "video_formats": unique_formats
            })
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
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
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{download_type}')
        temp_path = temp_file.name
        temp_file.close()
        
        if download_type == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality.replace('kbps', ''),
                }],
                'outtmpl': temp_path.replace('.audio', ''),
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['android']}},
            }
        else:
            height = quality.replace('p', '')
            ydl_opts = {
                'format': f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]',
                'outtmpl': temp_path,
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                'extractor_args': {'youtube': {'player_client': ['android']}},
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if download_type == 'audio':
                if filename.endswith(('.webm', '.m4a')):
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                elif not filename.endswith('.mp3'):
                    filename = filename + '.mp3'
            
            safe_title = re.sub(r'[^\w\-_\. ]', '', info.get('title', 'video'))[:100]
            download_name = f"{safe_title}.{download_type == 'video' and 'mp4' or 'mp3'}"
            
            return send_file(
                filename,
                as_attachment=True,
                download_name=download_name,
                mimetype=download_type == 'video' and 'video/mp4' or 'audio/mpeg'
            )
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
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
