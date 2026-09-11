/** 鎖倉分期時間軸（SVG，含 3 期標記與已付 %） */
import { lockTimelineMarkers } from '../../lib/billingChartData';
import type { LockInstallment } from '../../types';

export default function LockTimelineChart({
  installment,
  height = 72,
}: {
  installment: LockInstallment | null;
  height?: number;
}) {
  const { days, markers, paidPct } = lockTimelineMarkers(installment);
  const empty = !installment || markers.length === 0;

  return (
    <div className="w-full" style={{ minHeight: height }}>
      {empty ? (
        <div className="flex h-full items-center justify-center text-[11px] text-[#636366]">暫無鎖倉分期</div>
      ) : (
        <>
          <div className="mb-1 flex items-center justify-between text-[10px] text-[#8E8E93]">
            <span>0 天</span>
            <span className="text-[#64D2FF]">已解鎖 {paidPct}%</span>
            <span>{days} 天</span>
          </div>
          <svg viewBox="0 0 320 40" className="w-full" role="img" aria-label="鎖倉分期時間軸">
            <line x1="16" y1="20" x2="304" y2="20" stroke="rgba(255,255,255,0.12)" strokeWidth="4" strokeLinecap="round" />
            <line
              x1="16"
              y1="20"
              x2={16 + (288 * paidPct) / 100}
              y2="20"
              stroke="#64D2FF"
              strokeWidth="4"
              strokeLinecap="round"
            />
            {markers.map((m) => {
              const x = 16 + (288 * m.day) / days;
              return (
                <g key={m.day}>
                  <circle
                    cx={x}
                    cy={20}
                    r={6}
                    fill={m.paid ? '#30D158' : '#1C1C1E'}
                    stroke={m.paid ? '#30D158' : '#64D2FF'}
                    strokeWidth={2}
                  />
                  <text x={x} y={36} textAnchor="middle" fill="#8E8E93" fontSize="9">
                    {m.label}
                  </text>
                </g>
              );
            })}
          </svg>
        </>
      )}
    </div>
  );
}
