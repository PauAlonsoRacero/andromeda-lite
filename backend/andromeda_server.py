"""andromeda_server.py — Entry point para PyInstaller."""
import sys
import os

data_dir = os.environ.get('ANDROMEDA_DATA_DIR',
    os.path.join(os.path.dirname(sys.executable if getattr(sys,'frozen',False) else __file__), 'data'))
os.makedirs(data_dir, exist_ok=True)

if not getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == '__main__':
    port = int(os.environ.get('ANDROMEDA_PORT', '8000'))
    uvicorn.run(
        'app:create_app',
        factory=True,
        host='127.0.0.1',
        port=port,
        log_level='warning',
    )
