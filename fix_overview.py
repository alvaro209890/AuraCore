import re

file_path = '/home/acer/Downloads/AuraCore/frontend/components/connection-dashboard.tsx'
with open(file_path, 'r') as f:
    code = f.read()

pattern = r'function OverviewTab\(\{.*?(?=function ObserverTab\(\{)'

replacement = """function OverviewTab({
  memory,
  latestSnapshot,
  projects,
  preview,
  previewTone,
  status,
  connectionError,
  memoryError,
  previewError,
  insightMetrics,
  onGoToObserver,
  onGoToMemory,
  onGoToChat,
}: {
  memory: MemoryCurrent | null;
  latestSnapshot: MemorySnapshot | null;
  projects: ProjectMemory[];
  preview: MemoryAnalysisPreview | null;
  previewTone: "emerald" | "amber" | "indigo" | "rose";
  status: ObserverStatus | null;
  connectionError: string | null;
  memoryError: string | null;
  previewError: string | null;
  insightMetrics: InsightMetric[];
  onGoToObserver: () => void;
  onGoToMemory: () => void;
  onGoToChat: () => void;
}) {
  const [subTab, setSubTab] = useState<"summary" | "mapping" | "engine">("summary");

  return (
    <div className="page-stack">
      <Card className="hero-panel">
        <div className="hero-copy">
          <div className="hero-kicker">
            <Brain size={14} />
            AuraCore Ativo
          </div>
          <h3>Seu cérebro expandido está monitorando sinais, extraindo contexto e reorganizando prioridades em tempo real.</h3>
          <p>
            O observador captura apenas contatos diretos, a memória consolida padrões do dono e o planejador mostra se
            uma nova leitura realmente compensa antes de gastar tokens.
          </p>
        </div>
        <div className="hero-actions">
          <button className="ac-secondary-button" onClick={onGoToObserver} type="button">
            <Eye size={15} />
            Ver Observador
          </button>
          <button className="ac-secondary-button" onClick={onGoToMemory} type="button">
            <Database size={15} />
            Planejar Leitura
          </button>
          <button className="ac-primary-button" onClick={onGoToChat} type="button">
            <MessageSquare size={15} />
            Falar com IA
          </button>
        </div>
      </Card>

      <div style={{ padding: "0 4px" }}>
        <SegmentedControl
          options={["Painel de Resumo", "Mapa Estrutural", "Métricas Engine"]}
          selected={
            subTab === "summary" ? "Painel de Resumo" : subTab === "mapping" ? "Mapa Estrutural" : "Métricas Engine"
          }
          onChange={(val) => {
            if (val === "Painel de Resumo") setSubTab("summary");
            if (val === "Mapa Estrutural") setSubTab("mapping");
            if (val === "Métricas Engine") setSubTab("engine");
          }}
        />
      </div>

      {subTab === "summary" ? (
        <>
          <div className="stats-grid modern-stats-grid">
            <ModernStatCard
              label="Observador"
              value={status?.connected ? "Online" : "Aguardando"}
              meta={status?.connected ? "Operacional" : "Sem sessão ativa"}
              icon={Eye}
              tone="emerald"
            />
            <ModernStatCard
              label="Conexão ativa"
              value={status?.owner_number ?? "Sem número"}
              meta="Dispositivo principal"
              icon={Smartphone}
            />
            <ModernStatCard
              label="Próxima leitura"
              value={preview ? `${preview.recommendation_score}%` : "--"}
              meta={preview?.recommendation_label ?? "Sem cálculo"}
              icon={Zap}
              tone={previewTone}
            />
            <ModernStatCard
              label="Mensagens salvas"
              value={preview ? String(preview.retained_message_count) : "--"}
              meta={preview ? `de ${preview.retention_limit} retidas` : "Aguardando preview"}
              icon={Database}
              tone="indigo"
            />
          </div>

          <Card>
            <SectionTitle title="Resumo do Dono (Atual)" icon={Fingerprint} />
            <p className="lead-copy">
              {memory?.life_summary?.trim()
                ? memory.life_summary
                : "Ainda não existe um perfil consolidado. Conecte o observador, deixe sinais suficientes chegarem e execute a primeira leitura."}
            </p>
          </Card>
        </>
      ) : null}

      {subTab === "mapping" ? (
        <Card>
          <SectionTitle title="Mapeamento Estrutural" icon={Brain} />
          <div className="dual-column-grid">
            <div className="signal-cluster">
              <h4>Áreas Fortes</h4>
              <SignalBlock
                title="Aprendizados Recentes"
                lines={latestSnapshot?.key_learnings ?? []}
                emptyLabel="Sem aprendizados recentes consolidados."
              />
              <SignalBlock
                title="Rotina Detectada"
                lines={latestSnapshot?.routine_signals ?? []}
                emptyLabel="Sem sinais fortes de rotina ainda."
              />
              <SignalBlock
                title="Preferências Operacionais"
                lines={latestSnapshot?.preferences ?? []}
                emptyLabel="Sem preferências consolidadas ainda."
              />
            </div>

            <div className="signal-cluster">
              <h4 className="amber">Pontos Frágeis</h4>
              <SignalBlock
                title="Lacunas Atuais"
                lines={latestSnapshot?.open_questions ?? []}
                emptyLabel="Sem lacunas críticas no momento."
                subtle
              />
              <SignalBlock
                title="Projetos em Contexto"
                lines={projects.slice(0, 3).map((project) => `${project.project_name}: ${project.status || "sem status claro"}`)}
                emptyLabel="Nenhum projeto relevante foi consolidado ainda."
                subtle
              />
            </div>
          </div>
        </Card>
      ) : null}

      {subTab === "engine" ? (
        <div className="dual-column-grid">
          <Card className="score-card-modern">
            <SectionTitle title="Leitura Recomendada" icon={BarChart3} />
            <div className="score-display-row">
              <span className="score-big">{preview?.recommendation_score ?? 0}</span>
              <span className="score-small">/ 100</span>
            </div>
            <ProgressBar value={preview?.recommendation_score ?? 0} tone={previewTone} />
            <p className="support-copy">
              {preview?.recommendation_summary ??
                "A barra sobe quando o banco acumulou contexto novo suficiente para justificar uma nova leitura do DeepSeek."}
            </p>
          </Card>

          <Card>
            <SectionTitle title="Sinais Recentes" icon={Activity} />
            <div className="progress-bar-stack">
              {insightMetrics.map((metric) => (
                <ProgressBar
                  key={metric.label}
                  value={metric.value}
                  max={Math.max(...insightMetrics.map((item) => item.value), 1)}
                  tone={metric.color === "zinc" ? "amber" : metric.color}
                  label={metric.label}
                />
              ))}
            </div>
          </Card>
        </div>
      ) : null}

      {connectionError ? <InlineError title="Falha na conexão" message={connectionError} /> : null}
      {memoryError ? <InlineError title="Falha na memória" message={memoryError} /> : null}
      {previewError ? <InlineError title="Falha no preview" message={previewError} /> : null}
    </div>
  );
}

"""

new_code = re.sub(pattern, replacement, code, flags=re.DOTALL)
with open(file_path, 'w') as f:
    f.write(new_code)

