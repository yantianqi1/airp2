interface DebugPanelProps {
  debugScores: Record<string, unknown> | null;
  queryUnderstanding: Record<string, unknown> | null;
}

export function DebugPanel({ debugScores, queryUnderstanding }: DebugPanelProps) {
  return (
    <section className="panel-group">
      <div className="glass-panel panel-block">
        <p className="panel-title">Debug Scores</p>
        <pre className="json-box">{JSON.stringify(debugScores || {}, null, 2)}</pre>
      </div>

      <div className="glass-panel panel-block">
        <p className="panel-title">Query Understanding</p>
        <pre className="json-box">{JSON.stringify(queryUnderstanding || {}, null, 2)}</pre>
      </div>
    </section>
  );
}
