RF Sentinel: Estação Terrestre Automatizada para Captura de Sinais de Satélite
O RF Sentinel é um sistema de estação terrestre projetado para rastrear, capturar e decodificar automaticamente sinais de satélites, com foco em satélites meteorológicos (NOAA) e na Estação Espacial Internacional (ISS). Ele oferece uma interface web para monitoramento e controle, permitindo a captura manual e agendada de sinais de radiofrequência (RF).

Funcionalidades
Rastreamento e Agendamento Automático: Calcula e agenda automaticamente as passagens de satélites visíveis com base em dados TLE (Two-Line Element).

Captura de Sinais: Utiliza um HackRF One para capturar sinais de RF, suportando modos RAW (I/Q), FM e AM.

Decodificação de Imagens APT: Decodifica em tempo real os sinais de satélites meteorológicos NOAA para gerar imagens visíveis (APT - Automatic Picture Transmission).

Interface Web de Controle: Um painel de controle web permite monitorar o status do sistema, visualizar capturas, agendar passagens e realizar capturas manuais.

Análise de Sinais: Oferece uma ferramenta de análise para visualizar o espectrograma de capturas RAW, ajudando na identificação de sinais.

Armazenamento e Gerenciamento: Salva os sinais capturados (arquivos .wav) e as imagens decodificadas em um banco de dados local (SQLite), com gerenciamento automático para limpeza de arquivos antigos.

Arquitetura
O sistema é composto por vários módulos que trabalham em conjunto:

Servidor Web (web.py): Construído com FastAPI, serve a interface do usuário e uma API para controle e monitoramento do sistema.

Agendador (utils/scheduler.py): Uma thread em segundo plano que baixa dados TLE, calcula as passagens de satélite e agenda as capturas.

Scanner (utils/scanner.py): Responsável por executar o hackrf_transfer e processar o stream de dados para salvar as capturas.

Gerenciador de SDR (utils/sdr_manager.py): Garante acesso seguro e exclusivo ao dispositivo HackRF, evitando conflitos.

Decodificador (utils/decoder.py): Processa os dados I/Q brutos das capturas de satélites NOAA para gerar as imagens APT.

Banco de Dados (utils/db.py): Utiliza SQLite para armazenar metadados sobre os sinais capturados, incluindo tipo, frequência, data e caminhos dos arquivos.

Estado da Aplicação (app_state.py): Gerencia o estado compartilhado entre a thread do agendador e o servidor web para garantir a comunicação e o controle adequados.

Instalação e Configuração
Pré-requisitos
Python 3

Ambiente Conda (RadioConda é recomendado para ter todas as dependências de SDR)

HackRF One com a biblioteca hackrf instalada.

Passos para Instalação
Clone o repositório:

Bash

git clone https://github.com/lucas-cardoso-gomes/rf_sentinel.git
cd rf_sentinel
Configure o ambiente:
É altamente recomendado o uso do RadioConda. O arquivo run.bat foi criado para simplificar a execução em ambiente Windows, limpando o PATH para evitar conflitos de DLL e ativando o ambiente Conda correto.

Instale as dependências Python:

Bash

pip install fastapi uvicorn "uvicorn[standard]" python-multipart Jinja2 skyfield numpy Pillow scipy
Configuração
Edite o arquivo config.json para ajustar os parâmetros da sua estação terrestre:

station: Latitude, longitude e elevação da sua localização.

sdr_settings: Configurações padrão do SDR, como a taxa de amostragem.

targets: Lista de satélites para rastrear. Você pode adicionar ou remover alvos, especificando:

name: Nome do satélite (deve corresponder ao nome no arquivo TLE).

tle_url: URL para o arquivo TLE que contém os dados do satélite.

frequency: Frequência de recepção em Hz.

capture_duration_seconds: Duração máxima da captura.

lna_gain, vga_gain: Ganhos do HackRF.

storage_management: Configurações para exclusão automática de capturas antigas.

Como Usar
Execute a aplicação:

No Windows, utilize o run.bat.

Em outros sistemas, certifique-se de que o ambiente Conda está ativado e execute:

Bash

python main.py
Acesse o Painel de Controle:
Abra o seu navegador e acesse http://127.0.0.1:8000.

Monitore e Controle:

Status do Sistema: Verifique se o HackRF está conectado e se o scanner está ativo.

Controle do Scanner: Pause ou retome o agendador de capturas automáticas.

Próxima Captura: Veja qual é o próximo satélite a ser gravado e o tempo restante.

Captura Manual: Configure e inicie uma captura manual a qualquer momento, ideal para gravar sinais que não estão na lista de alvos.

Histórico de Capturas: Visualize, baixe ou exclua as gravações anteriores. Para capturas RAW, um link de "Analisar" estará disponível para ver o espectrograma.

Descrição dos Arquivos
<details>
<summary>Clique para ver a descrição detalhada dos arquivos</summary>

Caminho do Arquivo	Descrição
main.py	Ponto de entrada da aplicação. Inicializa o banco de dados, a thread do agendador e o servidor web Uvicorn.
web.py	Contém a lógica do servidor web FastAPI, definindo todos os endpoints da API e as rotas para a interface HTML.
app_state.py	Módulo central para gerenciar o estado compartilhado entre as diferentes partes da aplicação, como o status do hardware e os logs.
config.json	Arquivo de configuração principal para definir a localização da estação, os alvos de satélite e as configurações do SDR.
run.bat	Script para facilitar a execução da aplicação em ambiente Windows, gerenciando o PATH e o ambiente Conda.
utils/scheduler.py	Implementa a classe Scheduler que gerencia o ciclo de vida do rastreamento de satélites, incluindo a atualização de TLEs e o agendamento de capturas.
utils/scanner.py	Contém a função perform_capture, que executa o hackrf_transfer e lida com o streaming de dados para a decodificação e salvamento.
utils/decoder.py	Implementa a decodificação em tempo real de sinais APT de satélites NOAA, convertendo o sinal de RF em uma imagem.
utils/analyzer.py	Fornece a funcionalidade para analisar arquivos .wav (capturas RAW) e gerar dados de espectrograma para visualização.
utils/db.py	Gerencia todas as interações com o banco de dados SQLite, incluindo a criação de tabelas e a inserção/exclusão de registros de sinais.
utils/sdr_manager.py	Garante o gerenciamento seguro do HackRF, utilizando um padrão Singleton para evitar que múltiplas partes do código acessem o dispositivo simultaneamente.
utils/sdr_utils.py	Funções auxiliares para configurar os parâmetros do HackRF (frequência, ganhos, etc.) antes de uma captura.
utils/logger.py	Módulo de logging centralizado que imprime mensagens no console e as mantém em um log compartilhado para exibição na interface web.
utils/win_dll_fix.py	Script específico para Windows que adiciona os diretórios de DLL do RadioConda ao PATH do sistema para garantir que as bibliotecas do SoapySDR e HackRF sejam encontradas.
tle.py	Funções para baixar e extrair informações de arquivos TLE a partir de URLs como as do Celestrak.
templates/index.html	A página principal do painel de controle, com todos os elementos da interface do usuário.
templates/analysis.html	A página de visualização da análise do espectrograma.
static/js/dashboard.js	Lógica JavaScript para o painel de controle, que busca dados da API e atualiza a interface dinamicamente.
static/js/analysis.js	Lógica JavaScript para a página de análise, que busca os dados do espectrograma e os desenha usando Plotly.js.
static/css/style.css	Folha de estilos para a interface web, utilizando classes de utilitários e um tema escuro.
.gitignore	Especifica os arquivos e diretórios a serem ignorados pelo Git, como capturas e arquivos de cache do Python.
signals.db	O arquivo de banco de dados SQLite onde os metadados das capturas são armazenados.
tle_cache/	Diretório onde os arquivos TLE baixados são armazenados em cache para evitar downloads repetidos.

Exportar para as Planilhas
</details>
