// static/js/dashboard.js
const RFSentinelApp = {
    elements: {},
    state: {},
    init() {
        this.elements = {
            hackrfStatusLed: document.getElementById('hackrf-status-led'),
            hackrfStatusText: document.getElementById('hackrf-status-text'),
            scannerStatusLed: document.getElementById('scanner-status-led'),
            scannerStatusText: document.getElementById('scanner-status-text'),
            toggleButton: document.getElementById('toggle-button'),
            toggleButtonText: document.getElementById('toggle-button-text'),
            signalsTable: document.getElementById('signals-table'),
            activityLog: document.getElementById('activity-log'),
            nextTarget: document.getElementById('next-target'),
            nextTime: document.getElementById('next-time'),
            nextCountdown: document.getElementById('next-countdown'),
            manualCaptureButton: document.getElementById('manual-capture-button'),
            manualCaptureButtonText: document.getElementById('manual-capture-button-text'),
            captureNameInput: document.getElementById('capture-name'),
            captureFreqInput: document.getElementById('capture-freq'),
            captureSampleRateInput: document.getElementById('capture-sample-rate'),
            captureDurationInput: document.getElementById('capture-duration'),
            captureModeInput: document.getElementById('capture-mode'),
            lnaGainInput: document.getElementById('lna-gain'),
            lnaGainValue: document.getElementById('lna-gain-value'),
            vgaGainInput: document.getElementById('vga-gain'),
            vgaGainValue: document.getElementById('vga-gain-value'),
            ampEnableInput: document.getElementById('amp-enable'),
            upcomingPassesTable: document.getElementById('upcoming-passes-table'),
        };
        this.state = { countdownInterval: null, lastLogLength: 0 };
        
        this.elements.toggleButton.addEventListener('click', () => this.api.toggleScanner());
        this.elements.manualCaptureButton.addEventListener('click', () => this.api.startManualCapture());
        this.elements.signalsTable.addEventListener('click', (event) => {
            const deleteButton = event.target.closest('.delete-btn');
            if (deleteButton) {
                const signalId = deleteButton.dataset.signalId;
                this.api.deleteSignal(signalId);
            }
        });
        this.elements.lnaGainInput.addEventListener('input', (e) => {
            this.elements.lnaGainValue.textContent = `${e.target.value} dB`;
        });
        this.elements.vgaGainInput.addEventListener('input', (e) => {
            this.elements.vgaGainValue.textContent = `${e.target.value} dB`;
        });

        this.updateLoop();
    },
    updateLoop() {
        this.api.fetchStatus();
        this.api.fetchSignals();
        this.api.fetchPasses();
        setInterval(() => this.api.fetchStatus(), 2000);
        setInterval(() => this.api.fetchSignals(), 10000);
        setInterval(() => this.api.fetchPasses(), 30000);
    },
    api: {
        async fetchStatus() {
            try {
                const response = await fetch('/api/status');
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                RFSentinelApp.ui.renderStatus(data);
            } catch (error) { console.error('Erro ao buscar status:', error); }
        },
        async fetchSignals() {
            try {
                const response = await fetch('/api/signals');
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const signals = await response.json();
                RFSentinelApp.ui.renderSignals(signals);
            } catch (error) { console.error('Erro ao buscar sinais:', error); }
        },
        async fetchPasses() {
            try {
                const response = await fetch('/api/passes');
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const passes = await response.json();
                RFSentinelApp.ui.renderPasses(passes);
            } catch (error) { console.error('Erro ao buscar passagens:', error); }
        },
        async toggleScanner() {
            try {
                const response = await fetch('/scanner/toggle', { method: 'POST' });
                if (!response.ok) {
                    throw new Error('Falha ao comunicar com o servidor.');
                }
                RFSentinelApp.api.fetchStatus();
            } catch (error) {
                console.error('Erro ao alternar scanner:', error);
                alert(`Não foi possível alterar o estado do scanner: ${error.message}`);
            }
        },
        async startManualCapture() {
            const { elements } = RFSentinelApp;
            elements.manualCaptureButton.disabled = true;
            elements.manualCaptureButtonText.textContent = 'Enviando...';
            try {
                const response = await fetch('/api/capture/manual', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: elements.captureNameInput.value,
                        frequency_mhz: elements.captureFreqInput.value,
                        duration_sec: elements.captureDurationInput.value,
                        sample_rate: parseFloat(elements.captureSampleRateInput.value),
                        mode: elements.captureModeInput.value,
                        lna_gain: parseInt(elements.lnaGainInput.value),
                        vga_gain: parseInt(elements.vgaGainInput.value),
                        amp_enabled: elements.ampEnableInput.checked
                    })
                });
                if (!response.ok) {
                    const err = await response.json();
                    alert(`Erro: ${err.error}`);
                }
            } catch (e) {
                alert('Falha ao enviar comando de captura.');
            }
        },
        async deleteSignal(signalId) {
            if (!confirm(`Tem certeza que deseja apagar o sinal ID ${signalId} e seus arquivos?`)) {
                return;
            }
            try {
                const response = await fetch(`/api/signal/delete/${signalId}`, {
                    method: 'DELETE'
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Falha ao apagar o sinal.');
                }
                RFSentinelApp.api.fetchSignals();
            } catch (error) {
                console.error('Erro ao apagar sinal:', error);
                alert(`Não foi possível apagar o sinal: ${error.message}`);
            }
        }
    },
    ui: {
        renderStatus(data) {
            const { elements } = RFSentinelApp;
            elements.hackrfStatusText.textContent = data.hackrf_status.status_text;
            elements.hackrfStatusLed.className = `status-led ${data.hackrf_status.connected ? 'status-active' : 'status-stopped'}`;
            elements.scannerStatusText.textContent = `Scanner: ${data.scanner_status}`;
            elements.scannerStatusLed.className = `status-led ${data.scanner_status === 'Ativo' ? 'status-active' : 'status-stopped'}`;
            elements.toggleButtonText.textContent = data.scanner_status === 'Ativo' ? 'Pausar Scanner' : 'Ativar Scanner';
            elements.toggleButton.className = `btn w-full justify-center ${data.scanner_status === 'Ativo' ? 'btn-danger' : 'btn-primary'}`;
            if (data.scheduler_log && data.scheduler_log.length !== RFSentinelApp.state.lastLogLength) {
                this.renderLogs(data.scheduler_log);
                RFSentinelApp.state.lastLogLength = data.scheduler_log.length;
            }
            if (data.next_pass) {
                const pass = data.next_pass;
                elements.nextTarget.textContent = pass.name;
                const startTime = new Date(pass.start_utc);
                elements.nextTime.textContent = startTime.toUTCString().substring(5, 25);
                this.updateCountdown(startTime);
            } else {
                elements.nextTarget.textContent = 'Nenhum';
                elements.nextTime.textContent = '--:--:--';
                elements.nextCountdown.textContent = 'Aguardando agendamento...';
                clearInterval(RFSentinelApp.state.countdownInterval);
            }
            const btn = elements.manualCaptureButton;
            const isCapturing = data.manual_capture_active || data.is_scheduler_capturing;
            btn.disabled = isCapturing;
            if (data.manual_capture_active) {
                elements.manualCaptureButtonText.textContent = 'Gravando Manualmente...';
            } else if (data.is_scheduler_capturing) {
                elements.manualCaptureButtonText.textContent = 'Captura Agendada Ativa';
            } else {
                elements.manualCaptureButtonText.textContent = 'Gravar Sinal';
            }
        },
        renderSignals(signals) {
            const { signalsTable } = RFSentinelApp.elements;
            let newContent = '';
            if (!signals || signals.length === 0) {
                newContent = '<tr><td colspan="6" class="text-center p-4 text-slate-400">Nenhuma captura registrada ainda.</td></tr>';
            } else {
                newContent = signals.map(signal => {
                    const freqMhz = (signal.frequency / 1e6).toFixed(3);
                    const utcDate = new Date(signal.timestamp.replace('_', 'T') + 'Z');
                    const localTimestamp = utcDate.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
                    const fileName = signal.filepath.split(/[\\\/]/).pop();
                    let imageCell = '<td class="p-3 text-center text-slate-500">N/A</td>';
                    if (signal.image_path) {
                        imageCell = `<td class="p-3 text-center"><a href="/${signal.image_path}" target="_blank" title="Ver imagem" class="text-indigo-400 hover:text-indigo-300 inline-block"><svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" /></svg></a></td>`;
                    }
                    const isRaw = signal.filepath.toLowerCase().includes('_raw.wav');
                    const analysisContent = isRaw 
                        ? `<a href="/analysis?id=${signal.id}" target="_blank" class="text-indigo-400 hover:underline mr-4">Analisar</a>`
                        : `<span class="text-slate-500 mr-4 cursor-not-allowed" title="Análise disponível apenas para capturas RAW">Analisar</span>`;
                    return `<tr class="border-b border-slate-700 hover:bg-slate-800/50" data-signal-id="${signal.id}"><td class="p-3 font-semibold text-slate-300">${signal.target}</td><td class="p-3">${freqMhz} MHz</td><td class="p-3">${localTimestamp}</td><td class="p-3"><a href="/${signal.filepath}" download class="text-blue-400 hover:underline flex items-center gap-2"><svg class="w-4 h-4" fill="none" stroke-width="1.5" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" /></svg>${fileName}</a></td>${imageCell}<td class="p-3 text-center">${analysisContent}<button class="text-red-400 hover:text-red-300 delete-btn" data-signal-id="${signal.id}" title="Apagar Sinal"><svg class="w-6 h-6 inline-block" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg></button></td></tr>`;
                }).join('');
            }
            if (signalsTable.innerHTML !== newContent) {
                signalsTable.innerHTML = newContent;
            }
        },
        renderPasses(passes) {
            const { upcomingPassesTable } = RFSentinelApp.elements;
            let newContent = '';
            if (!passes || passes.length === 0) {
                newContent = '<tr><td colspan="4" class="text-center p-4 text-slate-400">Nenhuma passagem agendada nos próximos 2 dias.</td></tr>';
            } else {
                newContent = passes.map(pass => {
                    const startDate = new Date(pass.start_utc);
                    const endDate = new Date(pass.end_utc);
                    const options = { timeZone: 'America/Sao_Paulo', hour12: false, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' };
                    const startTimeLocal = startDate.toLocaleString('pt-BR', options);
                    const endTimeLocal = endDate.toLocaleString('pt-BR', options);
                    const durationMs = endDate - startDate;
                    const durationMinutes = Math.floor(durationMs / 60000);
                    const durationSeconds = Math.floor((durationMs % 60000) / 1000);
                    const durationStr = `${durationMinutes}m ${durationSeconds}s`;
                    return `<tr class="border-b border-slate-700 hover:bg-slate-800/50">
                                <td class="p-3 font-semibold text-slate-300">${pass.name}</td>
                                <td class="p-3">${startTimeLocal}</td>
                                <td class="p-3">${endTimeLocal}</td>
                                <td class="p-3">${durationStr}</td>
                            </tr>`;
                }).join('');
            }
            if (upcomingPassesTable.innerHTML !== newContent) {
                upcomingPassesTable.innerHTML = newContent;
            }
        },
        renderLogs(logs) {
            const logColors = {'INFO': 'text-sky-400', 'SUCCESS': 'text-green-400', 'WARN': 'text-yellow-400', 'ERROR': 'text-red-400', 'DEBUG': 'text-purple-400'};
            RFSentinelApp.elements.activityLog.innerHTML = logs.map(log => `<div class="flex"><span class="text-slate-500 mr-2 flex-shrink-0">[${log.timestamp}]</span><span class="${logColors[log.level] || 'text-slate-400'}">${log.message}</span></div>`).join('');
            RFSentinelApp.elements.activityLog.scrollTop = RFSentinelApp.elements.activityLog.scrollHeight;
        },
        updateCountdown(targetDate) {
            clearInterval(RFSentinelApp.state.countdownInterval);
            const update = () => {
                const diff = targetDate - new Date();
                if (diff <= 0) {
                    RFSentinelApp.elements.nextCountdown.textContent = "Captura em andamento...";
                    clearInterval(RFSentinelApp.state.countdownInterval);
                    return;
                }
                const h = Math.floor(diff / 3.6e6);
                const m = Math.floor((diff % 3.6e6) / 6e4);
                const s = Math.floor((diff % 6e4) / 1000);
                RFSentinelApp.elements.nextCountdown.textContent = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
            };
            update();
            RFSentinelApp.state.countdownInterval = setInterval(update, 1000);
        }
    }
};

document.addEventListener('DOMContentLoaded', () => RFSentinelApp.init());