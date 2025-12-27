'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Mic, Square, Loader2, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react';

interface TranscriptSegment {
  text: string;
  start: number;
  end: number;
}

export default function LiveRecordingPage() {
  const router = useRouter();

  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [duration, setDuration] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const isPausedRef = useRef(false);

  // Keep isPausedRef in sync with isPaused state
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  const stopRecording = useCallback((closeWebSocket = true) => {
    // Stop duration timer
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
      durationIntervalRef.current = null;
    }

    // Stop audio processing
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    // Stop media stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    // Send stop message but DON'T close WebSocket yet - wait for session_end
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'stop' }));
      // WebSocket will be closed when we receive session_end message
      if (closeWebSocket) {
        // Only close immediately if explicitly requested (e.g., cleanup on unmount)
        wsRef.current.close();
        wsRef.current = null;
      }
    }

    setIsRecording(false);
    setIsPaused(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Cleanup function
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
      if (processorRef.current) {
        processorRef.current.disconnect();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const startRecording = async () => {
    setError(null);
    setIsConnecting(true);

    try {
      // Get microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // Connect to WebSocket (directly to backend, not through Next.js proxy)
      const wsUrl = `ws://localhost:8000/streaming/live`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'session_start':
            setSessionId(data.session_id);
            setIsConnecting(false);
            setIsRecording(true);
            startAudioCapture(stream);
            startDurationTimer();
            break;

          case 'transcript':
            setTranscript((prev) => [
              ...prev,
              {
                text: data.text,
                start: data.start,
                end: data.end,
              },
            ]);
            break;

          case 'session_end':
            console.log('Session ended:', data);
            // Now it's safe to close the WebSocket
            if (wsRef.current) {
              wsRef.current.close();
              wsRef.current = null;
            }
            break;

          case 'error':
            setError(data.message);
            break;

          case 'keepalive':
            // Ignore keepalives
            break;
        }
      };

      ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        setError('Connection error. Please try again.');
        setIsConnecting(false);
      };

      ws.onclose = () => {
        console.log('WebSocket closed');
        setIsRecording(false);
      };
    } catch (err: any) {
      console.error('Error starting recording:', err);
      setError(err.message || 'Failed to start recording');
      setIsConnecting(false);
    }
  };

  const startAudioCapture = (stream: MediaStream) => {
    // Create audio context for processing
    const audioContext = new AudioContext({ sampleRate: 16000 });
    audioContextRef.current = audioContext;

    const source = audioContext.createMediaStreamSource(stream);

    // Create processor to get raw audio data
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;

    processor.onaudioprocess = (event) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      if (isPausedRef.current) return;

      const inputData = event.inputBuffer.getChannelData(0);

      // Convert float32 to int16
      const int16Data = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      // Send as binary data
      wsRef.current.send(int16Data.buffer);
    };

    source.connect(processor);
    processor.connect(audioContext.destination);
  };

  const startDurationTimer = () => {
    const startTime = Date.now();
    durationIntervalRef.current = setInterval(() => {
      setDuration(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
  };

  const saveRecording = async () => {
    if (!sessionId) return;

    setIsSaving(true);
    setError(null);

    try {
      const title = `Live Recording - ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString()}`;

      const res = await fetch(`/api/streaming/live/${sessionId}/save?title=${encodeURIComponent(title)}`, {
        method: 'POST',
      });

      if (res.ok) {
        const data = await res.json();
        router.push(`/meetings/${data.meeting_id}`);
      } else {
        const errorData = await res.json();
        setError(errorData.detail || 'Failed to save recording');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to save recording');
    } finally {
      setIsSaving(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <a href="/" className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-4">
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to meetings
        </a>
        <h1 className="text-2xl font-bold text-gray-900">Live Recording</h1>
        <p className="text-gray-600 mt-1">Record and transcribe a meeting in real-time</p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
          <p className="text-red-700">{error}</p>
        </div>
      )}

      {/* Recording Controls */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {!isRecording && !sessionId && (
              <button
                onClick={startRecording}
                disabled={isConnecting}
                className="flex items-center gap-2 px-6 py-3 bg-red-600 text-white rounded-full hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isConnecting ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Connecting...
                  </>
                ) : (
                  <>
                    <Mic className="h-5 w-5" />
                    Start Recording
                  </>
                )}
              </button>
            )}

            {isRecording && (
              <>
                <button
                  onClick={() => stopRecording(false)}
                  className="flex items-center gap-2 px-6 py-3 bg-gray-800 text-white rounded-full hover:bg-gray-900 transition-colors"
                >
                  <Square className="h-5 w-5" />
                  Stop
                </button>

                <div className="flex items-center gap-2">
                  <span className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
                  </span>
                  <span className="font-mono text-lg">{formatDuration(duration)}</span>
                </div>
              </>
            )}

            {!isRecording && sessionId && (
              <div className="flex items-center gap-4">
                <button
                  onClick={saveRecording}
                  disabled={isSaving}
                  className="flex items-center gap-2 px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="h-5 w-5" />
                      Save Recording
                    </>
                  )}
                </button>

                <button
                  onClick={() => {
                    setSessionId(null);
                    setTranscript([]);
                    setDuration(0);
                  }}
                  className="px-4 py-2 text-gray-600 hover:text-gray-900"
                >
                  Discard
                </button>

                <span className="text-gray-500">Duration: {formatDuration(duration)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Live Transcript */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">Live Transcript</h2>
        </div>
        <div className="p-6 min-h-[300px] max-h-[500px] overflow-y-auto">
          {transcript.length === 0 ? (
            <div className="text-center text-gray-500 py-12">
              {isRecording ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
                  <p>Listening...</p>
                </div>
              ) : (
                <p>Transcript will appear here as you speak</p>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {transcript.map((segment, idx) => (
                <div key={idx} className="flex gap-3">
                  <span className="text-xs text-gray-400 w-12 flex-shrink-0 pt-1">
                    {formatTime(segment.start)}
                  </span>
                  <p className="text-gray-800">{segment.text}</p>
                </div>
              ))}
              <div ref={transcriptEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Instructions */}
      {!isRecording && !sessionId && (
        <div className="mt-6 p-4 bg-blue-50 rounded-lg">
          <h3 className="font-medium text-blue-900 mb-2">How it works</h3>
          <ol className="list-decimal list-inside space-y-1 text-blue-800 text-sm">
            <li>Click "Start Recording" to begin</li>
            <li>Allow microphone access when prompted</li>
            <li>Speak clearly - your words will be transcribed in real-time</li>
            <li>Click "Stop" when finished, then save your recording</li>
          </ol>
        </div>
      )}
    </div>
  );
}
