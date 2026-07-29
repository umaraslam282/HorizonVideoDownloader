Horizon Video Downloader
Horizon Video Downloader is a commercial-grade, full-stack media extraction and management suite designed for high-speed downloading, precise format conversion, and complete local control. Built around a high-performance FastAPI backend and powered by industry-standard engines, it handles everything from single YouTube streams to complex multi-item social media carousels.

🚀 Key Features
Advanced YouTube Engine: Powered by yt-dlp with dynamic stream selection, real-time speed/ETA tracking, automatic subtitle embedding (.srt), and smart leftover cleanup.

Social Media Gallery Scraper: Built-in gallery-dl integration for Facebook and Instagram posts/reels, complete with an interactive media preview grid and selective downloading.

Persistent History & Analytics (SQLite): Automatically logs every download, title, source URL, timestamp, and status into a local history.db to track activity across app restarts.

Real-Time WebSocket Terminal Logs: Stream live debug logs, subprocess outputs, and error handling directly into the built-in UI terminal tab.

Granular Format & Container Controls:

Support for Video formats (MP4, MKV, MOV, WEBM, AVI) with automatic codec translation and smart fallback rules.

Support for Lossless Audio extraction (MP3, FLAC, WAV, OPUS, M4A).

Image format options (Original, JPG, PNG, WEBP, GIF) for social media downloads.

Authentication Pipeline: Full manual cookies.txt support to seamlessly bypass login walls or age-restricted media blocks without locking OS files.

Persistent Settings: Remembers your preferences and directory selections via browser storage.

🛠️ Architecture & Tech Stack
Backend: Python, FastAPI, Uvicorn, WebSockets, SQLite.

Core Downloader Binaries: yt-dlp, gallery-dl, FFmpeg / FFprobe, Deno runtime environment.

Frontend: Modern responsive HTML5/CSS3 glass-panel UI with vanilla JavaScript architecture.

⚙️ Installation & Local Setup
Prerequisites
Make sure you have Python 3.10+ installed on your system along with the required core binaries (ffmpeg.exe, gallery-dl.exe) placed in your project root directory.

1. Clone or Extract the Repository
Bash
cd Horizon_Video_Downloader
2. Install Dependencies
Bash
pip install -r requirements.txt
(If a requirements file isn't present, manually ensure FastAPI, Uvicorn, and curl-cffi are installed).

3. Run the Application
Start the FastAPI server:

Bash
python main.py
4. Access the Dashboard
Open your web browser and navigate to:

Plaintext
http://127.0.0.1:80
📦 Building a Standalone .EXE & Installer
If you want to package the app into a standalone desktop application with an installation wizard:

1. Compile with PyInstaller
Make sure your ffmpeg.exe, gallery-dl.exe, and icon.ico are in the root folder, then run:

Bash
pyinstaller build.spec
This builds your portable bundle inside the dist/HorizonDownloader/ directory.

2. Build the Inno Setup Installer
Download and open Inno Setup.

Open the provided installer.iss script.

Click Compile to generate your standalone setup executable: HorizonDownloader_Setup_v5.exe.
