@echo off
echo ============================================
echo      INICIANDO RF-SENTINEL (Modo Isolado)
echo ============================================
echo.

:: --- Limpeza do Ambiente ---
echo Limpando o PATH para evitar conflitos de DLL...
:: Define um PATH mínimo, apenas com o essencial do Windows
set "PATH=%SystemRoot%\system32;%SystemRoot%;%SystemRoot%\System32\Wbem"

:: --- Ativação do Conda ---
echo Ativando ambiente RadioConda...
call C:\ProgramData\radioconda\Scripts\activate.bat

:: --- Execução da Aplicação ---
echo.
echo Iniciando a aplicacao Python no ambiente limpo...
python main.py

echo.
echo Aplicacao finalizada.
pause