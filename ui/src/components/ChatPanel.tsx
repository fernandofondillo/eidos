import { useState, useRef, useEffect } from 'react';
import { ChatResponse } from '../hooks/useEidosApi';

interface ChatPanelProps {
  messages: ChatResponse[];
  onSend: (message: string) => void;
  thinking: boolean;
}

export function ChatPanel({ messages, onSend, thinking }: ChatPanelProps) {
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, thinking]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !thinking) {
      onSend(input.trim());
      setInput('');
    }
  };

  return (
    <div className="panel flex flex-col h-[500px]">
      <div className="border-b border-eidos-border px-4 py-2 flex items-center gap-2">
        <span className="text-sm font-bold">💬 Chat</span>
        <span className="text-xs text-eidos-muted">— habla con EIDOS</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !thinking && (
          <div className="text-center text-eidos-muted py-8">
            <p className="text-sm">Escribe un mensaje para empezar.</p>
            <p className="text-xs mt-2">
              Prueba: "conviértete en experto en Kubernetes" para disparar génesis de cápsula.
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {thinking && (
          <div className="flex items-center gap-2 text-eidos-muted text-sm">
            <span className="animate-pulse">🧠</span>
            <span>EIDOS está pensando...</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={handleSubmit} className="border-t border-eidos-border p-3 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Escribe tu mensaje..."
          className="input flex-1"
          disabled={thinking}
        />
        <button type="submit" className="btn-primary" disabled={thinking || !input.trim()}>
          Enviar
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatResponse }) {
  const rewardColor = msg.reward_delta >= 0 ? 'text-eidos-primary' : 'text-eidos-danger';
  const routeColor: Record<string, string> = {
    respond_direct: 'bg-eidos-primary text-black',
    search_memory: 'bg-eidos-accent text-black',
    request_clarification: 'bg-eidos-warning text-black',
    delegate_cortex: 'bg-eidos-border text-eidos-text',
    delegate_mesh: 'bg-eidos-border text-eidos-text',
    safety_block: 'bg-eidos-danger text-white',
  };

  return (
    <div className="space-y-1">
      <div className="bg-eidos-bg border border-eidos-border rounded-lg p-3">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span className={`badge ${routeColor[msg.route_type] || 'bg-eidos-border'}`}>
            {msg.route_type}
          </span>
          <span className="badge bg-eidos-border text-eidos-text">
            backend: {msg.monologue_backend}
          </span>
          <span className="text-xs text-eidos-muted">
            conf: {(msg.confidence * 100).toFixed(0)}%
          </span>
          <span className={`text-xs ${rewardColor}`}>
            reward Δ {msg.reward_delta >= 0 ? '+' : ''}{msg.reward_delta.toFixed(4)}
          </span>
        </div>
        <pre className="text-sm whitespace-pre-wrap font-mono text-eidos-text">
          {msg.text}
        </pre>
        {msg.evolution_event && (
          <div className="mt-2 p-2 bg-eidos-surface border border-eidos-primary rounded text-xs">
            🧬 <strong>Evolution triggered:</strong> {msg.evolution_event.topic} →{' '}
            <span className="text-eidos-primary">{msg.evolution_event.decision}</span>
          </div>
        )}
      </div>
    </div>
  );
}
