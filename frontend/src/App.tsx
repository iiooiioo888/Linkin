/**
 * 應用殼只掛四個入口。對話在 routes/mounts/chat.ts；
 * 其餘三個掛載由別的分支提供，缺檔時顯示「尚未接上」。
 */
import Shell from './routes/Shell';

export default function App() {
  return <Shell />;
}
