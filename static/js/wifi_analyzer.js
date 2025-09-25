document.addEventListener('DOMContentLoaded', () => {
    const bandButtons = document.querySelectorAll('.band-selector button');
    const startBtn = document.getElementById('start-scan-btn');
    const stopBtn = document.getElementById('stop-scan-btn');
    const statusText = document.getElementById('status-text');
    const plotContainer = document.getElementById('plot-container');

    let selectedBand = null;
    let websocket = null;
    let traces = []; // Array para armazenar os últimos 10 traces
    let currentTraceIndex = 0;
    let lastFreq = 0;

    // Inicializa o gráfico Plotly
    const layout = {
        title: 'Análise de Espectro com Histórico (Últimas 10 Varreduras)',
        xaxis: { title: 'Frequência (MHz)' },
        yaxis: { title: 'Intensidade (dBm)', range: [-100, 0] },
        plot_bgcolor: '#1e1e1e',
        paper_bgcolor: '#1e1e1e',
        font: { color: '#ffffff' },
        showlegend: false
    };
    Plotly.newPlot(plotContainer, [], layout);

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

            // Limpa o histórico de varreduras
            traces = [];
            lastFreq = 0;
            Plotly.react(plotContainer, [], layout);
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.error) {
                console.error('Erro do servidor:', data.error);
                statusText.textContent = `Erro: ${data.error}`;
                stopScan();
                return;
            }

            // Detecta o início de uma nova varredura quando a frequência reseta
            if (data.freq_mhz < lastFreq) {
                // Adiciona a varredura completa ao histórico
                if (traces.length >= 10) {
                    traces.shift(); // Remove a mais antiga
                }

                // Cria um novo trace para a nova varredura
                traces.push({
                    x: [],
                    y: [],
                    type: 'scatter',
                    mode: 'lines',
                    line: { color: 'rgba(0, 255, 0, 1)' } // Verde sólido para a nova
                });

                // Atualiza as cores e opacidades do histórico
                updateTraceColors();
            }

            lastFreq = data.freq_mhz;

            if (traces.length === 0) {
                // Inicia o primeiro trace
                 traces.push({
                    x: [],
                    y: [],
                    type: 'scatter',
                    mode: 'lines',
                    line: { color: 'rgba(0, 255, 0, 1)' }
                });
            }

            // Adiciona o ponto de dados ao trace atual (o último do array)
            const currentTrace = traces[traces.length - 1];
            currentTrace.x.push(data.freq_mhz);
            currentTrace.y.push(data.dbm);

            // Re-renderiza o gráfico com todos os traces
            Plotly.react(plotContainer, traces, layout);
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

    stopBtn.addEventListener('click', stopScan);

    function stopScan() {
        if (websocket) {
            websocket.close();
            statusText.textContent = 'Varredura parada pelo usuário.';
        }
    }

    function updateTraceColors() {
        const totalTraces = traces.length;
        traces.forEach((trace, i) => {
            const opacity = 1 - (totalTraces - 1 - i) * 0.1;
            trace.line.color = `rgba(0, 255, 0, ${Math.max(0.1, opacity)})`;
        });
    }

    function resetControls() {
        websocket = null;
        startBtn.disabled = !selectedBand;
        stopBtn.disabled = true;
        bandButtons.forEach(btn => btn.disabled = false);
        // Limpa o gráfico quando a varredura é parada ou perdida
        Plotly.react(plotContainer, [], layout);
    }
});