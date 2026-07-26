import { useState, useCallback } from 'react';
import { useEidosApi, useEidosWebSocket, ChatResponse, Monologue } from './hooks/useEidosApi';
import { Header } from './components/Header';
import { ChatPanel } from './components/ChatPanel';
import { MonologueViewer } from './components/MonologueViewer';
import { MemoryStatsPanel } from './components/MemoryStatsPanel';
import { CapsulesManager } from './components/CapsulesManager';
import { MeshMap } from './components/MeshMap';
import { RewardChart } from './components/RewardChart';
import { EvolutionPanel } from './components/EvolutionPanel';

export default function App() {
  const api = useEidosApi();
  const [messages, setMessages] = useState<ChatResponse[]>([]);
  const [currentMonologue, setCurrentMonologue] = useState<Monologue | null>(null);
  const [thinking, setThinking] = useState(false);
  const [wsMessages, setWsMessages] = useState<any[]>([]);

  const handleWSMessage = useCallback((msg: any) => {
    setWsMessages(prev => [...prev, msg]);
    if (msg.type === 'monologue' && msg.data) {
      setCurrentMonologue(msg.data as Monologue);
    }
    if (msg.type === 'response' && msg.data) {
      setMessages(prev => [...prev, msg.data as ChatResponse]);
      setThinking(false);
    }
    if (msg.type === 'error') {
      console.error('WS error:', msg.error);
      setThinking(false);
    }
  }, []);

  const { connected, send } = useEidosWebSocket(handleWSMessage);

  const handleSend = useCallback((message: string) => {
    setThinking(true);
    setCurrentMonologue(null);
    if (connected) {
      send({ type: 'chat', message });
    } else {
      // Fallback a REST si WS no está conectado
      api.sendChat(message).then(resp => {
        setMessages(prev => [...prev, resp]);
        if (resp.monologue) setCurrentMonologue(resp.monologue);
        setThinking(false);
      }).catch(err => {
        console.error('Chat error:', err);
        setThinking(false);
      });
    }
  }, [connected, send, api]);

  return (
    <div className="min-h-screen flex flex-col">
      <Header health={api.health} wsConnected={connected} mesh={api.mesh} />
      
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 p-4">
        {/* Columna izquierda: Chat + Monólogo */}
        <div className="lg:col-span-2 space-y-4">
          <ChatPanel
            messages={messages}
            onSend={handleSend}
            thinking={thinking}
          />
          <MonologueViewer monologue={currentMonologue} />
        </div>

        {/* Columna derecha: Paneles de estado */}
        <div className="space-y-4">
          <MemoryStatsPanel stats={api.stats} />
          <RewardChart motivation={api.motivation} />
          <MeshMap mesh={api.mesh} />
          <CapsulesManager
            capsules={api.capsules}
            onForge={api.forgeCapsule}
            onApprove={api.approveDraft}
            onReject={api.rejectDraft}
            onRefresh={api.refreshAll}
          />
          <EvolutionPanel evolution={api.evolution} />
        </div>
      </div>
    </div>
  );
}
