/** 分層 OPC 金字塔標誌 — L4 金鑽 / L3 藍三角 / L2 青點 + 紅色探詢鑽 */
export default function OpcPyramidLogo({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 56 72"
      width="56"
      height="72"
      aria-hidden="true"
      role="img"
    >
      <defs>
        <filter id="opc-logo-halo" x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor="#c9a961" floodOpacity="0.45" />
        </filter>
      </defs>

      <g filter="url(#opc-logo-halo)">
        {/* L4 → L3 金色連線 */}
        <line x1="28" y1="22" x2="16" y2="36" stroke="#c9a961" strokeWidth="1" opacity="0.55" />
        <line x1="28" y1="22" x2="28" y2="36" stroke="#c9a961" strokeWidth="1" opacity="0.55" />
        <line x1="28" y1="22" x2="40" y2="36" stroke="#c9a961" strokeWidth="1" opacity="0.55" />

        {/* L3 → L2 藍色連線 */}
        <line x1="16" y1="40" x2="14" y2="54" stroke="#7a92b8" strokeWidth="1" opacity="0.5" />
        <line x1="16" y1="40" x2="28" y2="58" stroke="#7a92b8" strokeWidth="1" opacity="0.5" />
        <line x1="28" y1="40" x2="20" y2="54" stroke="#7a92b8" strokeWidth="1" opacity="0.5" />
        <line x1="28" y1="40" x2="36" y2="54" stroke="#7a92b8" strokeWidth="1" opacity="0.5" />
        <line x1="40" y1="40" x2="28" y2="58" stroke="#7a92b8" strokeWidth="1" opacity="0.5" />
        <line x1="40" y1="40" x2="42" y2="54" stroke="#7a92b8" strokeWidth="1" opacity="0.5" />

        {/* L4 金色旋轉方塊（中空鑽石） */}
        <g transform="translate(28, 14) rotate(45)">
          <rect x="-10" y="-10" width="20" height="20" fill="#c9a961" rx="1" />
          <rect x="-5" y="-5" width="10" height="10" fill="#111116" rx="0.5" />
        </g>

        {/* L3 三個藍色三角 */}
        <polygon points="16,36 12,44 20,44" fill="#7a92b8" opacity="0.9" />
        <polygon points="28,36 24,44 32,44" fill="#7a92b8" opacity="0.9" />
        <polygon points="40,36 36,44 44,44" fill="#7a92b8" opacity="0.9" />

        {/* L2 六個青色執行點 */}
        <circle cx="14" cy="54" r="2.5" fill="#5fb8c9" />
        <circle cx="20" cy="54" r="2.5" fill="#5fb8c9" />
        <circle cx="36" cy="54" r="2.5" fill="#5fb8c9" />
        <circle cx="42" cy="54" r="2.5" fill="#5fb8c9" />
        <circle cx="22" cy="62" r="2.5" fill="#5fb8c9" />
        <circle cx="34" cy="62" r="2.5" fill="#5fb8c9" />

        {/* L2 中心紅色探詢鑽 */}
        <g transform="translate(28, 58) rotate(45)">
          <rect x="-3.5" y="-3.5" width="7" height="7" fill="#c47a7a" rx="0.5" />
        </g>
      </g>
    </svg>
  );
}
