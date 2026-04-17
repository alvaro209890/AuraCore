import { ManualInfoCard, ManualStep, formatDateTime } from '../../connection-dashboard';
import { Activity, AlertCircle, BarChart3, Brain, CheckCircle2, ChevronRight, Database, Eye, FileText, Fingerprint, FolderGit2, GitBranch, MessageSquare, Pause, Play, Plus, RefreshCw, Send, Server, Settings, Smartphone, Sparkles, Terminal, User, Users, X, XCircle, Zap, Clock } from 'lucide-react';
import { hasEstablishedMemory, buildActivityThinking, buildActivityTrace, getIntentTitle, getStepVisualState, MemorySignalCard, formatTokenCount, formatShortDateTime, formatRelativeTime, SectionTitle, ModernStatCard, ProgressBar, getProactiveStatusLabel, getProactiveCategoryLabel, formatConfidence, getProactiveDecisionLabel, truncateText, isProjectManuallyCompleted, getProjectStrength, normalizeProjectSearchText, getProjectStatusTone, getProjectStatusLabel, getAudienceLabel, ProjectInfoBlock, SegmentedControl, getRelationSortPriority, normalizeRelationType, getRelationTypeLabel, getRelationTone, getRelationStrength, AutomationNumberField } from '../../connection-dashboard';
import { useState } from 'react';
import type { MemoryCurrent, MemorySnapshot, ObserverStatus, ProjectMemory } from '@/lib/api';

export default function ManualTab({
  status,
  memory,
  projects,
  snapshots,
  automationStatus,
}: {
  status: ObserverStatus | null;
  memory: MemoryCurrent | null;
  projects: ProjectMemory[];
  snapshots: MemorySnapshot[];
  automationStatus: any;
}) {
  const [manualSubTab, setManualSubTab] = useState<"overview" | "flow" | "architecture" | "data" | "operations">("overview");
  const latestSnapshot = snapshots[0] ?? null;
  const memoryReady = Boolean(memory?.last_analyzed_at);
  const projectCount = projects.length;
  const manualTabs = [
    "Visao Geral",
    "Fluxo Real",
    "Arquitetura",
    "Dados",
    "Operacao",
  ];

  return (
    <div className="page-stack">
      <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm manual-hero-card">
        <div className="manual-hero-copy">
          <div className="hero-kicker">
            <FileText size={14} />
            Central de Operacao
          </div>
          <h3>O AuraCore e um operador de contexto pessoal em cima do WhatsApp.</h3>
          <p>
            Ele conecta o observador, filtra conversas uteis, consolida memoria do dono, salva memoria por
            pessoa e organiza projetos. Grupos so entram depois da base inicial e apenas quando voce ativa na aba Grupos.
          </p>
        </div>
        <div className="manual-hero-stats">
          <ModernStatCard
            label="Observador"
            value={status?.connected ? "Online" : "Pendente"}
            meta={status?.connected ? "Capturando diretas e grupos observados" : "Conecte o WhatsApp primeiro"}
            icon={Eye}
            tone="emerald"
          />
          <ModernStatCard
            label="Memoria Base"
            value={memoryReady ? "Pronta" : "Nao criada"}
            meta={memoryReady ? `Desde ${formatShortDateTime(memory?.last_analyzed_at ?? null)}` : "Primeira analise ainda nao foi rodada"}
            icon={Database}
            tone="indigo"
          />
          <ModernStatCard
            label="Memorias por pessoa"
            value={String(projectCount > 0 || snapshots.length > 0 ? "Ativas" : "Vazias")}
            meta="Atualizadas progressivamente por contato"
            icon={User}
            tone="amber"
          />
        </div>
      </div>

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={manualTabs}
          selected={
            manualSubTab === "overview"
              ? "Visao Geral"
              : manualSubTab === "flow"
                ? "Fluxo Real"
                : manualSubTab === "architecture"
                  ? "Arquitetura"
                  : manualSubTab === "data"
                    ? "Dados"
                    : "Operacao"
          }
          onChange={(value: any) => {
            if (value === "Visao Geral") setManualSubTab("overview");
            if (value === "Fluxo Real") setManualSubTab("flow");
            if (value === "Arquitetura") setManualSubTab("architecture");
            if (value === "Dados") setManualSubTab("data");
            if (value === "Operacao") setManualSubTab("operations");
          }}
        />
      </div>

      {manualSubTab === "overview" ? (
        <>
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Como Ler Este Produto" icon={Brain} />
            <div className="manual-grid">
              <div className="manual-list">
                <p>O site e dividido em duas camadas. A primeira e operacional: conectar o WhatsApp, ler mensagens, acompanhar a fila e ver os jobs. A segunda e cognitiva: consolidar memoria, mapear projetos e conversar com contexto.</p>
                <p>O Observador cuida da entrada. A Memoria cuida da consolidacao. Projetos guardam o que merece sobreviver. Atividade mostra o que o backend fez ou esta fazendo.</p>
              </div>
              <div className="manual-list">
                <p>Para o usuario final, a ideia e simples: conectar, fazer a primeira analise, puxar mensagens novas quando quiser e rodar a analise manual para manter o contexto vivo.</p>
                <p>Para voce localizar qualquer problema, pense assim: entrada de dados em Observador, consolidacao em Memoria, armazenamento no banco local e leitura do estado em Atividade.</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Mapa Das Abas" icon={Database} />
            <div className="manual-grid">
              <ManualInfoCard title="Visao Geral" text="Painel-resumo do estado atual: conexao, memoria, projetos, sinais e atalhos para o fluxo principal." icon={BarChart3} tone="indigo" />
              <ManualInfoCard title="Observador" text="Ponto de entrada do WhatsApp. Mostra QR, estado da instancia, sessao e a saude da captura." icon={Eye} tone="emerald" />
              <ManualInfoCard title="Grupos" text="Lista os grupos vistos no historico sincronizado. Todos nascem desativados e so entram na memoria incremental quando voce ativa." icon={Users} tone="amber" />
              <ManualInfoCard title="Memoria" text="Aqui nasce e evolui a memoria central. Primeira analise, lotes economicos de mensagens novas, estado da fila e resumo do dono." icon={Database} tone="indigo" />
              <ManualInfoCard title="Projetos" text="Organiza frentes reais detectadas nas conversas, com resumo, status, evidencias e proximos passos." icon={FolderGit2} tone="emerald" />
              <ManualInfoCard title="Atividade" text="Mostra o pipeline trabalhando: logs, lotes, trilha de execucao e o melhor raciocinio operacional salvo." icon={Activity} tone="emerald" />
              <ManualInfoCard title="Atividade Manual" text="Mostra syncs recentes, jobs manuais e execucoes de modelo persistidas no backend." icon={Terminal} tone="zinc" />
            </div>
          </div>
        </>
      ) : null}

      {manualSubTab === "flow" ? (
        <>
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Fluxo Real Do Site" icon={Terminal} />
            <div className="manual-sequence">
              <ManualStep title="1. Conectar o observador" text="Voce gera o QR, conecta o WhatsApp e libera a captura. A partir daqui o sistema passa a receber somente o que interessa para memoria." icon={Eye} tone="emerald" />
              <ManualStep title="2. Filtrar a entrada" text="Nem tudo entra. A ingestao evita status, broadcast, newsletter e lixo sem texto relevante. Conversas diretas entram por padrao; grupos ficam opt-in para leituras futuras." icon={Activity} tone="indigo" />
              <ManualStep title="3. Criar a memoria base" text="A primeira analise e manual e usa uma selecao balanceada das mensagens diretas mais relevantes e recentes." icon={Database} tone="amber" />
              <ManualStep title="4. Atualizar por contato" text="Durante as analises, o sistema tenta entender com quem e cada conversa e atualiza memorias separadas por pessoa." icon={User} tone="indigo" />
              <ManualStep title="5. Processar em lotes" text="Depois da base inicial, o backend passa a trabalhar em lotes economicos de mensagens novas." icon={RefreshCw} tone="emerald" />
              <ManualStep title="6. Salvar o que dura" text="O processamento atualiza resumo do dono, snapshots e projetos." icon={FolderGit2} tone="amber" />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Botoes Principais" icon={Zap} />
            <div className="manual-grid">
              <ManualInfoCard title="Puxar Novas Mensagens" text="Forca uma releitura das conversas recentes e atualiza a fila operacional no banco." icon={RefreshCw} tone="indigo" />
              <ManualInfoCard title="Primeira Analise" text="Cria a base inicial da memoria quando o sistema ainda nao conhece bem o dono." icon={Play} tone="emerald" />
              <ManualInfoCard title="Executar Analise" text="Usa as mensagens pendentes mais a memoria ja salva para atualizar resumo e projetos de forma incremental." icon={Sparkles} tone="indigo" />
              <ManualInfoCard title="Nova Conversa" text="Abre uma nova thread de conversa mantendo a memoria central e o historico salvo." icon={Plus} tone="amber" />
              <ManualInfoCard title="Rodar Tick" text="Executa o ciclo da automacao manualmente: fecha syncs, registra decisoes e tenta processar a fila." icon={Zap} tone="emerald" />
            </div>
          </div>
        </>
      ) : null}

      {manualSubTab === "architecture" ? (
        <>
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Arquitetura Em Camadas" icon={Server} />
            <div className="manual-grid">
              <ManualInfoCard title="Frontend" text="O painel organiza as abas de operacao, memoria, atividade e outras. Ele consulta a API e mostra o estado persistido do sistema." icon={Smartphone} tone="indigo" />
              <ManualInfoCard title="Backend FastAPI" text="Coordena observador, memoria, automacao e persistencia. E onde ficam as regras de selecao de mensagens." icon={Server} tone="emerald" />
              <ManualInfoCard title="Banco local SQLite" text="Armazena mensagens operacionais, snapshots, persona, projetos, memorias por pessoa e trilhas." icon={Database} tone="amber" />
              <ManualInfoCard title="Modelos de IA" text="O motor de analise consolida memoria usando o contexto salvo do banco de dados local." icon={Brain} tone="indigo" />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Como Cada Parte Se Conversa" icon={GitBranch} />
            <div className="manual-list">
              <p>Observador envia mensagens para o backend. O backend decide o que entra em `mensagens`, separa diretas de grupos e atualiza a fila operacional.</p>
              <p>A Memoria seleciona uma janela ou um lote, monta o prompt com contexto consolidado e grava de volta os resultados mais importantes.</p>
              <p>A analise nao le o WhatsApp cru. Ela trabalha em cima da memoria consolidada, dos projetos e dos sinais duraveis.</p>
              <p>A Automacao observa se existe memoria base, conta mensagens novas e enfileira no maximo um lote automatico por ciclo quando faz sentido.</p>
            </div>
          </div>
        </>
      ) : null}

      {manualSubTab === "data" ? (
        <>
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="O Que Vai Para O Banco Local" icon={Database} />
            <div className="manual-grid">
              <ManualInfoCard title="mensagens" text="Fila operacional de mensagens aproveitaveis." icon={MessageSquare} tone="zinc" />
              <ManualInfoCard title="persona & snapshots" text="Resumo principal do dono e historico consolidado." icon={Fingerprint} tone="emerald" />
              <ManualInfoCard title="person_memories" text="Memoria separada por contato ou participante progressivamente." icon={User} tone="amber" />
              <ManualInfoCard title="project_memories" text="Projetos, frentes, entregas com base nas conversas." icon={FolderGit2} tone="indigo" />
              <ManualInfoCard title="Logs do motor" text="Auditoria operacional sincronizada, processada e executada." icon={Activity} tone="emerald" />
              <ManualInfoCard title="wa_sessions" text="Estado de sessao e chaves locais." icon={Eye} tone="zinc" />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="O Que Nunca Deve Subir" icon={XCircle} />
            <div className="manual-list">
              <p>Grupos, canais, newsletter, broadcast e status.</p>
              <p>Ruido sem valor contextual, lixo sem texto util e mensagens puramente sistemicas.</p>
              <p>Explicacoes internas do pipeline na interface final quando elas nao ajudam o usuario a operar o sistema.</p>
            </div>
          </div>
        </>
      ) : null}

      {manualSubTab === "operations" ? (
        <>
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Estado Atual Da Operacao" icon={Activity} />
            <div className="manual-grid">
              <ManualInfoCard
                title="Observador"
                text={status?.connected ? `Conectado com ${status.owner_number ?? "numero ainda nao lido"}.` : "Desconectado ou aguardando leitura do QR."}
              />
              <ManualInfoCard
                title="Memoria Central"
                text={
                  memory?.last_analyzed_at
                    ? `Ultima consolidacao em ${formatDateTime(memory.last_analyzed_at)}.`
                    : "Ainda sem consolidacao inicial."
                }
                icon={memory?.last_analyzed_at ? Database : AlertCircle}
                tone={memory?.last_analyzed_at ? "indigo" : "amber"}
              />
              <ManualInfoCard
                title="Ultimo Snapshot"
                text={
                  latestSnapshot
                    ? `Ultima janela consolidada em ${formatShortDateTime(latestSnapshot.created_at)} com ${latestSnapshot.source_message_count} mensagens.`
                    : "Nenhum snapshot consolidado ainda."
                }
                icon={latestSnapshot ? Fingerprint : Brain}
                tone={latestSnapshot ? "emerald" : "zinc"}
              />
              <ManualInfoCard
                title="Projetos e Threads"
                text={`${projectCount} projeto(s) consolidado(s).`}
              />
              <ManualInfoCard
                title="Fila Manual"
                text={
                  automationStatus
                    ? `${automationStatus.queued_jobs_count} job(s) na fila e ${automationStatus.running_job_id ? "1 execucao em andamento" : "nenhuma execucao rodando agora"}.`
                    : "Status da atividade manual ainda nao carregado."
                }
                icon={automationStatus?.running_job_id ? Zap : Clock}
                tone={automationStatus?.running_job_id ? "emerald" : "zinc"}
              />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm">
            <SectionTitle title="Como Diagnosticar Rapido" icon={AlertCircle} />
            <div className="manual-grid">
              <ManualInfoCard title="Sem mensagens" text="Olhe primeiro a aba Observador e a releitura manual." icon={AlertCircle} tone="amber" />
              <ManualInfoCard title="Sem memoria base" text="Rode manualmente a primeira analise na aba Memoria." icon={Database} tone="indigo" />
              <ManualInfoCard title="Fila travada" text="Use Atividade e Automacao para ver rastro." icon={Terminal} tone="zinc" />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
