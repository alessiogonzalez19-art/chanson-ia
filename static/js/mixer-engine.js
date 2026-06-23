/**
 * MixerEngine — Web Audio API DAW Engine
 * 8-track mixer with EQ, effects, master bus, VU meters
 */
class MixerEngine {
    constructor(trackCount = 8) {
        this.trackCount = trackCount;
        this.ctx = null;
        this.masterGain = null;
        this.masterCompressor = null;
        this.masterLimiter = null;
        this.analyserMasterL = null;
        this.analyserMasterR = null;
        this.tracks = {};
        this.isPlaying = false;
        this.startTime = 0;
        this.pauseOffset = 0;
        this.loopStart = 0;
        this.loopEnd = null;
        this.loopEnabled = false;
        this.bpm = 120;
        this._rafId = null;
        this.onLevelUpdate = null; // callback(slot, level)
        this.onMasterLevel = null; // callback(L, R)
        this.onTimeUpdate = null;  // callback(position)
    }

    async init() {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        
        // Master chain: Gain -> Compressor -> Limiter -> Splitter -> Destination
        this.masterGain = this.ctx.createGain();
        this.masterGain.gain.value = 0.8;

        this.masterCompressor = this.ctx.createDynamicsCompressor();
        this.masterCompressor.threshold.value = -18;
        this.masterCompressor.knee.value = 6;
        this.masterCompressor.ratio.value = 3;
        this.masterCompressor.attack.value = 0.003;
        this.masterCompressor.release.value = 0.1;

        this.masterLimiter = this.ctx.createDynamicsCompressor();
        this.masterLimiter.threshold.value = -1;
        this.masterLimiter.knee.value = 0;
        this.masterLimiter.ratio.value = 20;
        this.masterLimiter.attack.value = 0.001;
        this.masterLimiter.release.value = 0.05;

        const splitter = this.ctx.createChannelSplitter(2);
        const mergerL = this.ctx.createGain();
        const mergerR = this.ctx.createGain();

        this.analyserMasterL = this.ctx.createAnalyser();
        this.analyserMasterL.fftSize = 256;
        this.analyserMasterR = this.ctx.createAnalyser();
        this.analyserMasterR.fftSize = 256;

        this.masterGain.connect(this.masterCompressor);
        this.masterCompressor.connect(this.masterLimiter);
        this.masterLimiter.connect(this.ctx.destination);
        this.masterLimiter.connect(splitter);
        splitter.connect(this.analyserMasterL, 0);
        splitter.connect(this.analyserMasterR, 1);

        // Initialize tracks
        for (let i = 1; i <= this.trackCount; i++) {
            this._initTrack(i);
        }

        this._startRAF();
        this.setupMIDI();
        return this;
    }

    setupMIDI() {
        if (navigator.requestMIDIAccess) {
            navigator.requestMIDIAccess().then(
                (midiAccess) => {
                    console.log("🎹 Web MIDI API connecté");
                    for (var input of midiAccess.inputs.values()) {
                        input.onmidimessage = this.onMIDIMessage.bind(this);
                    }
                },
                () => console.warn("MIDI access failed")
            );
        }
    }

    onMIDIMessage(message) {
        const command = message.data[0];
        const cc = message.data[1];
        const velocity = (message.data.length > 2) ? message.data[2] : 0;
        
        // 176 is typically CC (Control Change) on channel 1
        if (command >= 176 && command <= 191) {
            // Map CC 1-8 to Faders 1-8
            if (cc >= 1 && cc <= 8) {
                const dB = (velocity / 127) * 72 - 60; // Map 0-127 to -60..+12 dB
                this.setVolume(cc, dB);
                // Update UI if available
                const fader = document.getElementById(`fader-${cc}`);
                if (fader) {
                    fader.value = dB;
                    const label = document.getElementById(`vol-label-${cc}`);
                    if (label) label.textContent = `${dB>0?'+':''}${dB.toFixed(1)}dB`;
                }
            }
            // Map CC 11-18 to Pan 1-8
            if (cc >= 11 && cc <= 18) {
                const trackId = cc - 10;
                const pan = (velocity / 127) * 2 - 1; // -1 to +1
                this.setPan(trackId, pan);
            }
        }
    }

    _initTrack(slot) {
        const gainNode = this.ctx.createGain();
        gainNode.gain.value = 0.8;

        const panNode = this.ctx.createStereoPanner();
        panNode.pan.value = 0;

        // 3-band EQ
        const eqLow = this.ctx.createBiquadFilter();
        eqLow.type = 'lowshelf';
        eqLow.frequency.value = 200;
        eqLow.gain.value = 0;

        const eqMid = this.ctx.createBiquadFilter();
        eqMid.type = 'peaking';
        eqMid.frequency.value = 1000;
        eqMid.Q.value = 1;
        eqMid.gain.value = 0;

        const eqHigh = this.ctx.createBiquadFilter();
        eqHigh.type = 'highshelf';
        eqHigh.frequency.value = 4000;
        eqHigh.gain.value = 0;

        const analyser = this.ctx.createAnalyser();
        analyser.fftSize = 256;

        const effectSend = this.ctx.createGain();
        effectSend.gain.value = 1;

        // Chain: gain -> pan -> eqLow -> eqMid -> eqHigh -> analyser -> effectSend -> masterGain
        gainNode.connect(panNode);
        panNode.connect(eqLow);
        eqLow.connect(eqMid);
        eqMid.connect(eqHigh);
        eqHigh.connect(analyser);
        analyser.connect(effectSend);
        effectSend.connect(this.masterGain);

        this.tracks[slot] = {
            gainNode, panNode, eqLow, eqMid, eqHigh, analyser, effectSend,
            source: null,
            buffer: null,
            muted: false,
            soloed: false,
            effects: {},
            name: `Track ${slot}`,
            waveformData: null
        };
    }

    async loadTrack(slot, audioUrl, trackName) {
        if (!this.ctx) await this.init();
        const wasPlaying = this.isPlaying;
        if (wasPlaying) this.pause();

        try {
            const response = await fetch(audioUrl);
            const arrayBuffer = await response.arrayBuffer();
            const audioBuffer = await this.ctx.decodeAudioData(arrayBuffer);
            
            if (this.tracks[slot].source) {
                this.tracks[slot].source.stop();
                this.tracks[slot].source.disconnect();
            }
            
            this.tracks[slot].buffer = audioBuffer;
            this.tracks[slot].name = trackName || `Track ${slot}`;
            this.tracks[slot].waveformData = this._computeWaveform(audioBuffer);

            if (wasPlaying) this.play();
            return { success: true, duration: audioBuffer.duration };
        } catch (e) {
            console.error(`Failed to load track ${slot}:`, e);
            return { success: false, error: e.message };
        }
    }

    _computeWaveform(buffer, samples = 200) {
        const rawData = buffer.getChannelData(0);
        const blockSize = Math.floor(rawData.length / samples);
        const peaks = [];
        for (let i = 0; i < samples; i++) {
            let max = 0;
            for (let j = 0; j < blockSize; j++) {
                const abs = Math.abs(rawData[i * blockSize + j]);
                if (abs > max) max = abs;
            }
            peaks.push(max);
        }
        return peaks;
    }

    removeTrack(slot) {
        const track = this.tracks[slot];
        if (!track) return;
        if (track.source) {
            try { track.source.stop(); } catch(e) {}
            track.source.disconnect();
        }
        track.buffer = null;
        track.source = null;
        track.name = `Track ${slot}`;
        track.waveformData = null;
    }

    play() {
        if (this.isPlaying) return;
        if (!this.ctx) return;
        if (this.ctx.state === 'suspended') this.ctx.resume();
        
        const offset = this.pauseOffset;
        
        Object.entries(this.tracks).forEach(([slot, track]) => {
            if (!track.buffer) return;
            const source = this.ctx.createBufferSource();
            source.buffer = track.buffer;
            source.connect(track.gainNode);
            source.start(0, offset % track.buffer.duration);
            if (this.loopEnabled) {
                source.loop = true;
                source.loopStart = this.loopStart;
                source.loopEnd = this.loopEnd || track.buffer.duration;
            }
            track.source = source;
        });
        
        this.startTime = this.ctx.currentTime - offset;
        this.isPlaying = true;
    }

    pause() {
        if (!this.isPlaying) return;
        this.pauseOffset = this.ctx.currentTime - this.startTime;
        Object.values(this.tracks).forEach(track => {
            if (track.source) {
                try { track.source.stop(); } catch(e) {}
                track.source = null;
            }
        });
        this.isPlaying = false;
    }

    stop() {
        this.pause();
        this.pauseOffset = 0;
    }

    seekTo(position) {
        const wasPlaying = this.isPlaying;
        if (wasPlaying) this.pause();
        this.pauseOffset = position;
        if (wasPlaying) this.play();
    }

    setLoop(start, end) {
        this.loopStart = start;
        this.loopEnd = end;
        this.loopEnabled = true;
    }

    getCurrentTime() {
        if (!this.isPlaying) return this.pauseOffset;
        return this.ctx.currentTime - this.startTime;
    }

    setVolume(slot, dB) {
        const track = this.tracks[slot];
        if (!track) return;
        const gain = dB <= -60 ? 0 : Math.pow(10, dB / 20);
        track.gainNode.gain.setTargetAtTime(gain, this.ctx.currentTime, 0.01);
    }

    setPan(slot, value) {
        const track = this.tracks[slot];
        if (!track) return;
        track.panNode.pan.setTargetAtTime(value, this.ctx.currentTime, 0.01);
    }

    setMute(slot, muted) {
        const track = this.tracks[slot];
        if (!track) return;
        track.muted = muted;
        track.gainNode.gain.setTargetAtTime(muted ? 0 : (track.soloed ? 1 : 0.8), this.ctx.currentTime, 0.01);
    }

    setSolo(slot, soloed) {
        const track = this.tracks[slot];
        if (!track) return;
        track.soloed = soloed;
        // Mute all others if soloing
        const anySolo = Object.values(this.tracks).some(t => t.soloed);
        Object.entries(this.tracks).forEach(([s, t]) => {
            const shouldHear = !anySolo || t.soloed;
            t.gainNode.gain.setTargetAtTime(shouldHear && !t.muted ? 0.8 : 0, this.ctx.currentTime, 0.01);
        });
    }

    setEQ(slot, low, mid, high) {
        const track = this.tracks[slot];
        if (!track) return;
        track.eqLow.gain.setTargetAtTime(low, this.ctx.currentTime, 0.01);
        track.eqMid.gain.setTargetAtTime(mid, this.ctx.currentTime, 0.01);
        track.eqHigh.gain.setTargetAtTime(high, this.ctx.currentTime, 0.01);
    }

    addEffect(slot, type, params = {}) {
        const track = this.tracks[slot];
        if (!track) return;
        
        let effectNode;
        switch(type) {
            case 'reverb': {
                const convolver = this.ctx.createConvolver();
                const length = this.ctx.sampleRate * (params.decay || 2);
                const impulse = this.ctx.createBuffer(2, length, this.ctx.sampleRate);
                for (let c = 0; c < 2; c++) {
                    const data = impulse.getChannelData(c);
                    for (let i = 0; i < length; i++) {
                        data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 2);
                    }
                }
                convolver.buffer = impulse;
                const wetGain = this.ctx.createGain();
                wetGain.gain.value = params.mix || 0.3;
                const dryGain = this.ctx.createGain();
                dryGain.gain.value = 1 - (params.mix || 0.3);
                // insert in chain: disconnect effectSend from master, route through reverb
                effectNode = { type, convolver, wetGain, dryGain };
                track.effects[type] = effectNode;
                break;
            }
            case 'delay': {
                const delay = this.ctx.createDelay(2.0);
                delay.delayTime.value = params.time || (60 / this.bpm / 4);
                const feedback = this.ctx.createGain();
                feedback.gain.value = params.feedback || 0.3;
                delay.connect(feedback);
                feedback.connect(delay);
                effectNode = { type, delay, feedback };
                track.effects[type] = effectNode;
                break;
            }
            case 'distortion': {
                const waveshaper = this.ctx.createWaveShaper();
                const amount = params.amount || 50;
                const curve = new Float32Array(256);
                for (let i = 0; i < 256; i++) {
                    const x = (i * 2) / 256 - 1;
                    curve[i] = ((Math.PI + amount) * x) / (Math.PI + amount * Math.abs(x));
                }
                waveshaper.curve = curve;
                effectNode = { type, waveshaper };
                track.effects[type] = effectNode;
                break;
            }
        }
    }

    removeEffect(slot, type) {
        const track = this.tracks[slot];
        if (track && track.effects[type]) {
            delete track.effects[type];
        }
    }

    setMasterVolume(dB) {
        if (!this.masterGain) return;
        const gain = dB <= -60 ? 0 : Math.pow(10, dB / 20);
        this.masterGain.gain.setTargetAtTime(gain, this.ctx.currentTime, 0.01);
    }

    setCompressor(threshold, ratio, attack, release) {
        if (!this.masterCompressor) return;
        this.masterCompressor.threshold.value = threshold;
        this.masterCompressor.ratio.value = ratio;
        this.masterCompressor.attack.value = attack;
        this.masterCompressor.release.value = release;
    }

    setLimiter(threshold) {
        if (!this.masterLimiter) return;
        this.masterLimiter.threshold.value = threshold;
    }

    getTrackLevel(slot) {
        const track = this.tracks[slot];
        if (!track || track.muted) return 0;
        const data = new Uint8Array(track.analyser.frequencyBinCount);
        track.analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128;
            sum += v * v;
        }
        return Math.sqrt(sum / data.length);
    }

    getMasterLevel() {
        const getLevel = (analyser) => {
            if (!analyser) return 0;
            const data = new Uint8Array(analyser.frequencyBinCount);
            analyser.getByteTimeDomainData(data);
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
                const v = (data[i] - 128) / 128;
                sum += v * v;
            }
            return Math.sqrt(sum / data.length);
        };
        return { L: getLevel(this.analyserMasterL), R: getLevel(this.analyserMasterR) };
    }

    getWaveformData(slot) {
        return this.tracks[slot]?.waveformData || [];
    }

    applyDirective(command) {
        const { action, track, value, band, effect, params } = command;
        switch(action) {
            case 'set_volume': this.setVolume(track, value); break;
            case 'set_pan': this.setPan(track, value); break;
            case 'set_mute': this.setMute(track, value); break;
            case 'set_solo': this.setSolo(track, value); break;
            case 'set_eq': {
                const t = this.tracks[track];
                if (t) {
                    const low = band === 'low' ? value : t.eqLow.gain.value;
                    const mid = band === 'mid' ? value : t.eqMid.gain.value;
                    const high = band === 'high' ? value : t.eqHigh.gain.value;
                    this.setEQ(track, low, mid, high);
                }
                break;
            }
            case 'add_effect': this.addEffect(track, effect, params || {}); break;
            case 'remove_effect': this.removeEffect(track, effect); break;
            case 'set_master_volume': this.setMasterVolume(value); break;
        }
    }

    _startRAF() {
        const tick = () => {
            if (this.onLevelUpdate) {
                Object.keys(this.tracks).forEach(slot => {
                    this.onLevelUpdate(parseInt(slot), this.getTrackLevel(parseInt(slot)));
                });
            }
            if (this.onMasterLevel) {
                const { L, R } = this.getMasterLevel();
                this.onMasterLevel(L, R);
            }
            if (this.onTimeUpdate && this.isPlaying) {
                this.onTimeUpdate(this.getCurrentTime());
            }
            this._rafId = requestAnimationFrame(tick);
        };
        this._rafId = requestAnimationFrame(tick);
    }

    destroy() {
        if (this._rafId) cancelAnimationFrame(this._rafId);
        if (this.ctx) this.ctx.close();
    }

    // Export via OfflineAudioContext
    async exportMix(durationSeconds) {
        const offlineCtx = new OfflineAudioContext(2, 44100 * durationSeconds, 44100);
        const offlineMaster = offlineCtx.createGain();
        offlineMaster.gain.value = 0.8;
        offlineMaster.connect(offlineCtx.destination);
        
        const loadPromises = Object.entries(this.tracks).map(async ([slot, track]) => {
            if (!track.buffer || track.muted) return;
            const source = offlineCtx.createBufferSource();
            source.buffer = track.buffer;
            const gain = offlineCtx.createGain();
            gain.gain.value = track.gainNode.gain.value;
            source.connect(gain);
            gain.connect(offlineMaster);
            source.start(0);
        });
        
        await Promise.all(loadPromises);
        const renderedBuffer = await offlineCtx.startRendering();
        
        // Convert to WAV blob
        const wav = audioBufferToWav(renderedBuffer);
        return new Blob([wav], { type: 'audio/wav' });
    }
}

// Simple WAV encoder
function audioBufferToWav(buffer) {
    const numChannels = buffer.numberOfChannels;
    const sampleRate = buffer.sampleRate;
    const format = 1; // PCM
    const bitDepth = 16;
    const bytesPerSample = bitDepth / 8;
    const blockAlign = numChannels * bytesPerSample;
    const numSamples = buffer.length;
    const dataSize = numSamples * blockAlign;
    const headerSize = 44;
    const arrayBuffer = new ArrayBuffer(headerSize + dataSize);
    const view = new DataView(arrayBuffer);
    const write = (offset, val, bytes) => {
        if (bytes === 2) view.setUint16(offset, val, true);
        else if (bytes === 4) view.setUint32(offset, val, true);
        else view.setUint8(offset, val);
    };
    'RIFF'.split('').forEach((c, i) => write(i, c.charCodeAt(0), 1));
    write(4, 36 + dataSize, 4);
    'WAVE'.split('').forEach((c, i) => write(8 + i, c.charCodeAt(0), 1));
    'fmt '.split('').forEach((c, i) => write(12 + i, c.charCodeAt(0), 1));
    write(16, 16, 4); write(20, format, 2); write(22, numChannels, 2);
    write(24, sampleRate, 4); write(28, sampleRate * blockAlign, 4);
    write(32, blockAlign, 2); write(34, bitDepth, 2);
    'data'.split('').forEach((c, i) => write(36 + i, c.charCodeAt(0), 1));
    write(40, dataSize, 4);
    const offset = 44;
    const channels = [];
    for (let c = 0; c < numChannels; c++) channels.push(buffer.getChannelData(c));
    for (let i = 0; i < numSamples; i++) {
        for (let c = 0; c < numChannels; c++) {
            const s = Math.max(-1, Math.min(1, channels[c][i]));
            view.setInt16(offset + (i * numChannels + c) * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
    }
    return arrayBuffer;
}

window.MixerEngine = MixerEngine;
