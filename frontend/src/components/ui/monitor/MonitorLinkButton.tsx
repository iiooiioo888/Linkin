import './monitor.css';

export function MonitorLinkButton({
  onClick,
  label = '前往',
  type = 'button',
  href,
}: {
  onClick?: () => void;
  label?: string;
  type?: 'button' | 'submit';
  href?: string;
}) {
  if (href) {
    return (
      <a href={href} className="mon-link-btn">
        {label}
      </a>
    );
  }
  return (
    <button type={type} onClick={onClick} className="mon-link-btn">
      {label}
    </button>
  );
}
