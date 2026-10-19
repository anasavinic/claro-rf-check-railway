# Executável Windows

Esta cópia gera um `.exe` no mesmo formato do Vivo RF Check: PyInstaller em um arquivo, sem console, pedindo permissão de administrador, e uma janela local (`pywebview`) em `127.0.0.1`.

Não usa Postgres, Redis, Celery, OBS nem o SSO do Core Connect. O banco SQLite e os uploads ficam em `%LOCALAPPDATA%\Claro RF Check`.

## Gerar o exe

No PowerShell, na raiz desta pasta, com Python 3.12 e Node.js:

```powershell
.\build_exe.ps1
```

O arquivo sai em `dist\ClaroRFCheck-dev.exe`. Numa tag do CI, o nome usa essa tag (`ClaroRFCheck-v1.0.0.exe`), como o `VivoRFCheck-<tag>.exe`.

Para abrir em desenvolvimento, sem empacotar:

```powershell
python -m pip install -r requirements-desktop.txt
python main.py
```

A janela entra direto na aplicação. O usuário local `desktop` é criado na subida e autenticado sozinho.

Se a janela não abrir, o erro fica em `%LOCALAPPDATA%\Claro RF Check\logs\startup.log`, `app.log` e `django.log`.
