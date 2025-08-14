document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const signalId = urlParams.get('id');
    
    const signalInfoEl = document.getElementById('signal-info');
    const specPlaceholder = document.getElementById('spectrogram-placeholder');
    const audioContainer = document.getElementById('audio-player-container');
    const audioPlayer = document.getElementById('audio-player');
    const audioPlaceholder = document.getElementById('audio-placeholder');
    const downloadLink = document.getElementById('download-link');

    if (!signalId) {
        signalInfoEl.textContent = 'Erro: ID do sinal não fornecido.';
        specPlaceholder.innerHTML = '<p class="text-2xl text-red-500">ID do sinal ausente na URL.</p>';
        audioPlaceholder.textContent = 'ID do sinal ausente na URL.';
        return;
    }

    fetch(`/api/signal/info/${signalId}`)
        .then(response => response.json())
        .then(info => {
            const utcDate = new Date(info.timestamp.replace('_', 'T') + 'Z');
            const localTimestamp = !isNaN(utcDate.getTime()) 
                ? utcDate.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' }) 
                : "Data Inválida";
            
            signalInfoEl.textContent = `Alvo: ${info.target} | Frequência: ${(info.frequency / 1e6).toFixed(3)} MHz | Capturado em: ${localTimestamp}`;
            
            if(info.filepath) {
                const audioUrl = `/captures/${info.filepath}`;
                audioPlayer.src = audioUrl;
                downloadLink.href = audioUrl;
                downloadLink.download = info.filepath.split(/[\\\/]/).pop();
                audioContainer.classList.remove('hidden');
                audioPlaceholder.classList.add('hidden');
            } else {
                audioPlaceholder.textContent = 'Arquivo de áudio não encontrado.';
            }
        });

    fetch(`/api/signal/analyze/${signalId}`)
        .then(response => response.json())
        .then(data => {
            if (data && data.spectrogram_db) {
                specPlaceholder.style.display = 'none';
                drawSpectrogram(data);
            } else { throw new Error('Dados de análise inválidos.'); }
        })
        .catch(err => {
             specPlaceholder.innerHTML = `<p class="text-2xl text-red-400">Falha ao carregar dados de análise.</p>`;
        });
});

function drawSpectrogram(data) {
    Plotly.newPlot('spectrogram-chart', [{
        z: data.spectrogram_db, x: data.times, y: data.frequencies.map(f => f / 1e6),
        type: 'heatmap', colorscale: 'Jet',
        colorbar: { title: 'Potência (dB)', titleside: 'right' }
    }], {
        title: 'Análise de Frequência vs. Tempo',
        xaxis: { title: 'Tempo (s)', gridcolor: '#334155' },
        yaxis: { title: 'Frequência (MHz)', gridcolor: '#334155' },
        paper_bgcolor: '#1e293b', plot_bgcolor: '#0f172a',
        font: { color: '#e2e8f0' },
        margin: { l: 60, r: 50, b: 50, t: 50 }
    }, {responsive: true});
}