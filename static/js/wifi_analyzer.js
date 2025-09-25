document.addEventListener('DOMContentLoaded', () => {
    const bandButtons = document.querySelectorAll('.band-selector button');
    const startBtn = document.getElementById('start-scan-btn');
    const stopBtn = document.getElementById('stop-scan-btn');
    const statusText = document.getElementById('status-text');
    const plotContainer = document.getElementById('plot-container');

    let selectedBand = null;
    let websocket = null;
    let spectrumData = {
        x: [],
        y: [],
        type: 'scatter',
        mode: 'lines',
        line: { color: '#007bff' }
    };

    // Inicializa o gráfico Plotly
    const layout = {
        title: 'Análise de Espectro em Tempo Real',
        xaxis: { title: 'Frequência (MHz)' },
        yaxis: { title: 'Intensidade (dBm)', range: [-100, 0] },
        plot_bgcolor: '#1e1e1e',
        paper_bgcolor: '#1e1e1e',
        font: { color: '#ffffff' }
    };
    Plotly.newPlot(plotContainer, [spectrumData], layout);

    bandButtons.forEach(button => {
        button.addEventListener('click', () => {
            if (websocket) return; // Não permite mudar de banda durante a varredura

            bandButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            selectedBand = button.getAttribute('data-band');
            startBtn.disabled = false;
            statusText.textContent = `Banda de ${selectedBand} GHz selecionada. Clique em "Iniciar Varredura".`;
        });
    });

    startBtn.addEventListener('click', () => {
        if (!selectedBand || websocket) return;

        const wsUrl = `ws://${window.location.host}/ws/wifi_scan/${selectedBand}`;
        websocket = new WebSocket(wsUrl);

        websocket.onopen = () => {
            console.log('Conexão WebSocket estabelecida.');
            statusText.textContent = `Varredura em andamento na banda de ${selectedBand} GHz...`;
            startBtn.disabled = true;
            stopBtn.disabled = false;
            bandButtons.forEach(btn => btn.disabled = true);

            // Limpa dados antigos ao iniciar uma nova varredura
            spectrumData.x = [];
            spectrumData.y = [];
            Plotly.redraw(plotContainer);
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.error) {
                console.error('Erro do servidor:', data.error);
                statusText.textContent = `Erro: ${data.error}`;
                stopScan();
                return;
            }

            // Encontra o índice da frequência para atualizar ou adicionar
            const index = spectrumData.x.indexOf(data.freq_mhz);
            if (index > -1) {
                spectrumData.y[index] = data.dbm;
            } else {
                // Adiciona o novo ponto de dados e mantém a ordem
                spectrumData.x.push(data.freq_mhz);
                spectrumData.y.push(data.dbm);

                // Ordena os arrays com base na frequência
                const sortedIndices = spectrumData.x.map((_, i) => i).sort((a, b) => spectrumData.x[a] - spectrumData.x[b]);
                spectrumData.x = sortedIndices.map(i => spectrumData.x[i]);
                spectrumData.y = sortedIndices.map(i => spectrumData.y[i]);
            }

            // Atualiza o gráfico de forma eficiente
            Plotly.react(plotContainer, [spectrumData], layout);
        };

        websocket.onclose = () => {
            console.log('Conexão WebSocket fechada.');
            if (!stopBtn.disabled) { // Se não foi o usuário que parou
                statusText.textContent = 'A conexão foi perdida. Por favor, tente novamente.';
            }
            resetControls();
        };

        websocket.onerror = (error) => {
            console.error('Erro no WebSocket:', error);
            statusText.textContent = 'Ocorreu um erro na conexão. Verifique o console.';
            resetControls();
        };
    });

    const stopScan = () => {
        if (websocket) {
            websocket.close();
            statusText.textContent = 'Varredura parada pelo usuário.';
        }
    };

    stopBtn.addEventListener('click', stopScan);

    function resetControls() {
        websocket = null;
        startBtn.disabled = !selectedBand;
        stopBtn.disabled = true;
        bandButtons.forEach(btn => btn.disabled = false);
    }
});