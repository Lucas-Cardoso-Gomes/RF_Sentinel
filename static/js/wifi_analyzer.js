// static/js/wifi_analyzer.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Referências aos Elementos da UI ---
    const bandButtons = document.querySelectorAll('.band-selector button');
    const startBtn = document.getElementById('start-scan-btn');
    const stopBtn = document.getElementById('stop-scan-btn');
    const statusText = document.getElementById('status-text');
    const plotContainer = document.getElementById('plot-container');

    // --- Estado da Aplicação ---
    let selectedBand = null;
    let websocket = null;
    let historyTraces = [];
    const MAX_HISTORY = 10;
    let lastDrawTime = 0;
    const DRAW_INTERVAL_MS = 100; // Limita a atualização do gráfico a cada 100ms

    // --- Configuração Inicial do Gráfico Plotly ---
    const layout = {
        title: 'Análise de Espectro em Tempo Real',
        xaxis: { title: 'Frequência (MHz)', gridcolor: 'rgba(255,255,255,0.1)' },
        yaxis: { title: 'Intensidade (dBm)', range: [-100, -10], gridcolor: 'rgba(255,255,255,0.1)' },
        plot_bgcolor: '#1e293b',
        paper_bgcolor: '#1e293b',
        font: { color: '#e2e8f0' },
        showlegend: false
    };
    Plotly.newPlot(plotContainer, [], layout);

    // --- Funções ---

    function updateUI(isScanning, message) {
        startBtn.disabled = isScanning || !selectedBand;
        stopBtn.disabled = !isScanning;
        bandButtons.forEach(btn => btn.disabled = isScanning);
        statusText.textContent = message;
    }

    function startScan() {
        if (!selectedBand || websocket) return;

        const wsUrl = `ws://${window.location.host}/ws/wifi_scan/${selectedBand}`;
        websocket = new WebSocket(wsUrl);
        
        updateUI(true, `Conectando para varrer a banda de ${selectedBand} GHz...`);
        historyTraces = [];

        websocket.onopen = () => {
            updateUI(true, `Varredura em andamento na banda de ${selectedBand} GHz...`);
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.error) {
                updateUI(false, `Erro: ${data.error}`);
                stopScan();
                return;
            }

            if (data.event === 'new_scan_started') {
                historyTraces.unshift({ x: [], y: [], type: 'scatter', mode: 'lines', line: { width: 2 } });
                if (historyTraces.length > MAX_HISTORY) historyTraces.pop();
                return;
            }
            
            // --- OTIMIZAÇÃO: Processa o lote de dados de uma vez ---
            if (data.type === 'spectrum_chunk' && historyTraces.length > 0) {
                const currentTrace = historyTraces[0];
                // Concatena os novos arrays de dados recebidos
                currentTrace.x = currentTrace.x.concat(data.freqs_mhz);
                currentTrace.y = currentTrace.y.concat(data.dbm_values);
            }

            // Limita a taxa de atualização do gráfico para evitar sobrecarga
            const now = Date.now();
            if (now - lastDrawTime > DRAW_INTERVAL_MS) {
                redrawPlot();
                lastDrawTime = now;
            }
        };

        websocket.onclose = () => {
            updateUI(false, 'Varredura parada. Selecione uma banda para começar.');
            websocket = null;
            redrawPlot(); // Desenha o último estado
        };

        websocket.onerror = (error) => {
            console.error('Erro no WebSocket:', error);
            updateUI(false, 'Ocorreu um erro na conexão.');
            websocket = null;
        };
    }

    function stopScan() {
        if (websocket) websocket.close();
    }
    
    function redrawPlot() {
        const tracesToPlot = historyTraces.map((trace, index) => {
            const opacity = 1.0 - (index * 0.1); 
            const color = index === 0 ? '#4f46e5' : '#475569';
            return { ...trace, line: { ...trace.line, color }, opacity };
        });

        // Ordena os pontos de cada traço para garantir a renderização correta
        tracesToPlot.forEach(trace => {
             const sortedPoints = trace.x.map((x, i) => ({x, y: trace.y[i]}))
                                        .sort((a, b) => a.x - b.x);
             trace.x = sortedPoints.map(p => p.x);
             trace.y = sortedPoints.map(p => p.y);
        });

        Plotly.react(plotContainer, tracesToPlot.reverse(), layout);
    }

    // --- Event Listeners ---
    bandButtons.forEach(button => {
        button.addEventListener('click', () => {
            if (websocket) return;
            bandButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            selectedBand = button.getAttribute('data-band');
            updateUI(false, `Banda de ${selectedBand} GHz selecionada. Clique em "Iniciar Varredura".`);
        });
    });

    startBtn.addEventListener('click', startScan);
    stopBtn.addEventListener('click', stopScan);
});