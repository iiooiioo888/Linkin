/**
 * 應用殼只掛四個入口。頁面來自 routes/mounts，缺檔時才顯示「尚未接上」。
 */
import Shell from './routes/Shell';

export default function App() {
  return <Shell />;
}
