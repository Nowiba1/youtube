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

# CORS configuration - Will be set via environment variable
ALLOWED_ORIGIN = os.environ.get('FRONTEND_URL', 'https://nowiba1.github.io')
CORS(app, origins=[ALLOWED_ORIGIN])

# Keep-alive configuration
def should_be_awake():
    """Return False between 00:00-07:00 UTC"""
    now = datetime.now(pytz.UTC)
    current_hour = now.hour
    return not (0 <= current_hour < 7)

def keep_alive():
    """Background thread to prevent Render sleep"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:10000')
    
    while True:
        if should_be_awake():
            try:
                requests.get(f"{app_url}/health", timeout=5)
                print(f"✓ Keep-alive ping at {datetime.now()}")
            except Exception as e:
                print(f"✗ Ping failed: {e}")
            time.sleep(840)  # 14 minutes
        else:
            print(f"💤 Sleep hours (00:00-07:00 UTC) - {datetime.now()}")
            time.sleep(3600)  # Check hourly during sleep

# Start keep-alive thread
threading.Thread(target=keep_alive, daemon=True).start()

@app.route('/health')
def health():
    return jsonify({
        "status": "awake",
        "time": str(datetime.now()),
        "sleep_hours": "00:00-07:00 UTC"
    })

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
            'extract_flat': False
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
            
            return jsonify({
                "title": info.get('title', 'Unknown'),
                "thumbnail": info.get('thumbnail', ''),
                "video_formats": formats
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    temp_file = None
    try:
        data = request.json
        url = data.get('url')
        download_type = data.get('type', 'video')
        quality = data.get('quality', '720p')
        
        # Create temp file
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
            }
        else:
            height = quality.replace('p', '')
            ydl_opts = {
                'format': f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]',
                'outtmpl': temp_path,
                'quiet': True,
                'merge_output_format': 'mp4'
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if download_type == 'audio':
                filename = filename.replace('.webm', '.mp3').replace('.m4a', '.mp3')
            
            # Clean filename for security
            safe_filename = re.sub(r'[^\w\-_\. ]', '', info.get('title', 'video'))
            download_name = f"{safe_filename}.{download_type == 'video' and 'mp4' or 'mp3'}"
            
            return send_file(
                filename,
                as_attachment=True,
                download_name=download_name,
                mimetype=download_type == 'video' and 'video/mp4' or 'audio/mpeg'
            )
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Cleanup temp file after sending
        if temp_file and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
