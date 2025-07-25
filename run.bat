@echo off
echo ============================================
echo      INICIANDO RF-SENTINEL
echo ============================================
echo.
echo Ativando ambiente RadioConda...
call C:\ProgramData\radioconda\Scripts\activate.bat
echo.
echo Iniciando a aplicacao Python...
python main.py
echo.
echo Aplicacao finalizada. Pressione qualquer tecla para sair.
pause