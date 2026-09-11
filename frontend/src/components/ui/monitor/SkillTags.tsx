import { skillTagColor } from '../../../lib/monitorData';
import './monitor.css';

export function SkillTags({ tags, max = 8 }: { tags: string[]; max?: number }) {
  const shown = tags.slice(0, max);
  if (shown.length === 0) {
    return <p className="text-[10px] text-[var(--console-faint)]">尚無技能標籤</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {shown.map((tag, i) => (
        <span key={tag} className="mon-skill-tag">
          <span className="mon-skill-tag__dot" style={{ background: skillTagColor(i) }} />
          {tag}
        </span>
      ))}
      {tags.length > max ? (
        <span className="mon-skill-tag text-[var(--console-faint)]">+{tags.length - max}</span>
      ) : null}
    </div>
  );
}
