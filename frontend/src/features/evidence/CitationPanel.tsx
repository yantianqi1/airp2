import type { Citation, WorldbookContext } from '../../shared/types/rp';

interface CitationPanelProps {
  citations: Citation[];
  context: WorldbookContext | null;
}

function formatCitation(citation: Citation): string {
  if (!citation.chapter) {
    return citation.source_id;
  }
  if (citation.scene_index === null || citation.scene_index === undefined) {
    return citation.chapter;
  }
  return `${citation.chapter} / scene ${citation.scene_index}`;
}

export function CitationPanel({ citations, context }: CitationPanelProps) {
  const facts = context?.facts || [];

  return (
    <section className="panel-group">
      <div className="glass-panel panel-block">
        <p className="panel-title">Citations</p>
        {citations.length === 0 ? <p className="muted">暂无引用</p> : null}
        <div className="stack-list">
          {citations.map((item) => (
            <article key={`${item.source_id}-${item.scene_index}-${item.chapter}`} className="evidence-item">
              <p className="evidence-head">{formatCitation(item)}</p>
              <p className="evidence-body">{item.excerpt}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="glass-panel panel-block">
        <p className="panel-title">Worldbook Facts</p>
        {facts.length === 0 ? <p className="muted">等待检索结果</p> : null}
        <div className="stack-list">
          {facts.map((item, idx) => (
            <article key={`${item.source_chapter}-${item.source_scene}-${idx}`} className="evidence-item">
              <p className="evidence-head">
                {item.source_chapter || 'unknown'}
                {item.source_scene !== null && item.source_scene !== undefined ? ` / scene ${item.source_scene}` : ''}
              </p>
              <p className="evidence-body">{item.fact_text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
