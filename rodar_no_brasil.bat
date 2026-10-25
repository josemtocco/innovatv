@echo off
REM ==================================================================
REM  Gera a lista innova.m3u a partir do SEU PC no Brasil (IP BR).
REM  Rodar daqui pega o catalogo completo e links que funcionam no BR.
REM ==================================================================
chcp 65001 >nul
cd /d "%~dp0"

REM --- (opcional) cole aqui os dados da sua conta / device ---
REM set INNOVA_DEVICE_ID=cole-aqui-o-device-id-do-seu-navegador
REM set INNOVA_LOGIN=seu-email
REM set INNOVA_SENHA=sua-senha
REM --- (opcional) usar um catalogo capturado no F12 em vez da API ---
REM set INNOVA_CATALOGO=%~dp0catalogo.json
REM set INNOVA_DEBUG=1
REM set VALIDAR_STREAMS=1
REM set USAR_SEED=1

where python >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Python nao encontrado no PATH.
  echo Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH".
  pause
  exit /b 1
)

python gerar_innova.py
echo.
echo ==================================================================
echo  Pronto. Lista gerada em playlists\innova.m3u
echo  Para publicar no GitHub:
echo     git add playlists\innova.m3u estado_canais.json
echo     git commit -m "Atualiza lista Innova"
echo     git push
echo ==================================================================
pause
