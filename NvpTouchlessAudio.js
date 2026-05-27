import React, { useState, useEffect, useRef } from 'react';

export default function NvpTouchlessAudio() {
  const [isListening, setIsListening] = useState(false);
  const [lastCommand, setLastCommand] = useState('');
  
  // Two distinct WebSockets
  const sttSocketRef = useRef(null);
  const brainSocketRef = useRef(null);
  const mediaRecorderRef = useRef(null);

  useEffect(() => {
    // 1. Connect to the Dedicated STT Engine (Port 8001)
    sttSocketRef.current = new WebSocket('ws://127.0.0.1:8001/ws/stream_mic');
    
    // 2. Connect to the Main NVP Brain (Port 8000)
    brainSocketRef.current = new WebSocket('ws://127.0.0.1:8000/ws/touchless_director');
    
    // 3. When STT finishes transcribing, send the text to the Brain
    sttSocketRef.current.onmessage = (event) => {
      const transcribedText = event.data;
      if (transcribedText) {
        setLastCommand(transcribedText);
        // Forward text to the main backend
        if (brainSocketRef.current?.readyState === WebSocket.OPEN) {
          brainSocketRef.current.send(transcribedText);
        }
      }
    };

    // 4. When the Brain replies with audio, play it
    brainSocketRef.current.onmessage = async (event) => {
      const audioBlob = new Blob([event.data], { type: 'audio/wav' });
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      await audio.play();
    };

    return () => {
      sttSocketRef.current?.close();
      brainSocketRef.current?.close();
    };
  }, []);

  const toggleMic = async () => {
    if (isListening) {
      mediaRecorderRef.current?.stop();
      setIsListening(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      
      mediaRecorderRef.current.ondataavailable = (event) => {
        // Stream 500ms audio chunks directly to the STT microservice
        if (event.data.size > 0 && sttSocketRef.current?.readyState === WebSocket.OPEN) {
          sttSocketRef.current.send(event.data);
        }
      };

      mediaRecorderRef.current.start(500);
      setIsListening(true);
    } catch (err) {
      console.error("Microphone hardware missing or denied.", err);
    }
  };

  return (
    <div className="p-4 border border-zinc-800 bg-black text-white rounded-lg flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-sm tracking-widest uppercase">Touchless Interface</h3>
          <p className="text-xs text-zinc-400">
            {isListening ? 'Mic Active - Transcribing...' : 'Standby'}
          </p>
        </div>
        <button 
          onClick={toggleMic}
          className={`px-6 py-2 rounded font-bold text-sm uppercase transition-colors ${
            isListening ? 'bg-red-900 hover:bg-red-800 text-red-200' : 'bg-zinc-800 hover:bg-zinc-700 text-white'
          }`}
        >
          {isListening ? 'Mute Mic' : 'Open Mic'}
        </button>
      </div>

      {/* Visual feedback so the Director knows what the AI heard */}
      {lastCommand && (
        <div className="bg-zinc-900 p-3 rounded border border-zinc-800">
          <p className="text-xs text-zinc-500 uppercase font-bold mb-1">Last Command Heard:</p>
          <p className="text-sm italic text-zinc-300">"{lastCommand}"</p>
        </div>
      )}
    </div>
  );
}