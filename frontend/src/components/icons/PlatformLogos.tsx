type PlatformLogoProps = {
  platform: 'telegram' | 'feishu' | 'dingtalk' | 'wework' | 'wechat' | 'qqbot' | 'onebot';
  className?: string;
};

export function PlatformLogo({ platform, className }: PlatformLogoProps) {
  switch (platform) {
    case 'telegram':
      return (
        <svg className={className} viewBox="0 0 240 240" aria-hidden="true">
          <defs>
            <linearGradient id="tg-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#37aee2" />
              <stop offset="100%" stopColor="#1e96c8" />
            </linearGradient>
          </defs>
          <circle cx="120" cy="120" r="120" fill="url(#tg-grad)" />
          <path fill="#c8daea" d="M98 175c-3.9 0-3.2-1.5-4.6-5.2L82 132.2 152.8 88l8.3 2.2-6.9 18.8L98 175z" />
          <path fill="#a9c9dd" d="M98 175c3 0 4.3-1.4 6-3 2.6-2.5 36-35 36-35l-20.5-5-19 12-2.5 30v1z" />
          <path fill="#fff" d="M100 144.4l48.4 35.7c5.5 3 9.5 1.5 10.9-5.1L179 82.2c2-8.1-3.1-11.7-8.4-9.3L55 117.5c-7.9 3.2-7.8 7.6-1.4 9.5l29.7 9.3L152 93c3.2-2 6.2-.9 3.8 1.3L100 144.4z" />
        </svg>
      );
    case 'dingtalk':
      return (
        <svg className={className} viewBox="0 0 1024 1024" aria-hidden="true">
          <path fill="#4285F4" d="M1024 155.733C1024 70.4 953.6 0 868.267 0H155.733C70.4 0 0 70.4 0 155.733v712.534C0 953.6 70.4 1024 155.733 1024h712.534C953.6 1024 1024 953.6 1024 868.267V155.733z" />
          <path fill="#FFF" d="M810.667 422.4c-2.134 6.4-4.267 14.933-8.534 23.467C774.4 505.6 701.867 620.8 701.867 620.8l-21.334 36.267h102.4L588.8 915.2l44.8-174.933h-78.933l27.733-115.2c-23.467 6.4-49.067 12.8-81.067 23.466 0 0-42.666 25.6-121.6-46.933 0 0-53.333-46.933-23.466-59.733 12.8-4.267 64-10.667 104.533-17.067 55.467-6.4 87.467-10.667 87.467-10.667s-168.534 2.134-206.934-4.266c-40.533-6.4-89.6-72.534-100.266-132.267 0 0-17.067-32 36.266-17.067s268.8 59.734 268.8 59.734-281.6-87.467-300.8-108.8c-19.2-21.334-55.466-115.2-51.2-172.8 0 0 2.134-14.934 17.067-10.667 0 0 209.067 96 352 147.2 140.8 53.333 264.533 81.067 247.467 147.2z" />
        </svg>
      );
    case 'feishu':
      return (
        <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
          <path fill="#00C2FF" d="M20 13c5.8-4.2 12.9-5.1 19.4-2.4l15.8 6.6-14.1 8.6c-5.8 3.5-13 4.2-19.3 1.9L8.6 22.9 20 13z" />
          <path fill="#3370FF" d="M48.8 24.7c4.8 5.2 6.3 12.2 4.1 18.7l-5.2 15.9-9.8-13.1c-4-5.3-5.3-12.2-3.6-18.7l3.7-14.5 10.8 11.7z" />
          <path fill="#2ED0A7" d="M15.1 50.7C9.5 46.3 6.7 39.7 7.6 32.9l2.2-17 11.6 11.5c4.7 4.7 7.2 11.2 6.8 17.8L27.4 60 15.1 50.7z" />
        </svg>
      );
    case 'wework':
      return (
        <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
          <path fill="#2F7DFF" d="M25 11c-8.8 0-16 6.5-16 14.6 0 4.6 2.3 8.8 6 11.5l-2.5 7.2 8.2-4.2c1.4.3 2.9.5 4.3.5 8.8 0 16-6.5 16-14.5S33.8 11 25 11z" />
          <path fill="#FFB200" d="M41.2 23.5c7.6 0 13.8 5.6 13.8 12.6 0 7-6.2 12.6-13.8 12.6-1.3 0-2.7-.2-3.9-.5l-7.4 3.8 2.2-6.5c-2.9-2.3-4.7-5.7-4.7-9.4 0-7 6.2-12.6 13.8-12.6z" />
          <circle cx="20" cy="26" r="2.3" fill="#fff" />
          <circle cx="28" cy="26" r="2.3" fill="#fff" />
          <circle cx="37" cy="36" r="2.1" fill="#fff" />
          <circle cx="44" cy="36" r="2.1" fill="#fff" />
        </svg>
      );
    case 'wechat':
      return (
        <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
          <path fill="#28C445" d="M26 12c10.5 0 19 6.8 19 15.3S36.5 42.5 26 42.5c-1.7 0-3.3-.2-4.8-.6L12 46l3.1-7.8c-5-2.7-8.1-6.8-8.1-11.6C7 18.8 15.5 12 26 12z" />
          <path fill="#9BE941" d="M45.5 28c6.9 0 12.5 4.6 12.5 10.3 0 5.8-5.6 10.4-12.5 10.4-1.1 0-2.2-.1-3.3-.4L35 52l2-5.3c-2.5-1.9-4-4.5-4-7.6C33 32.6 38.6 28 45.5 28z" />
          <circle cx="20.5" cy="27" r="2.1" fill="#fff" />
          <circle cx="31.5" cy="27" r="2.1" fill="#fff" />
          <circle cx="41.5" cy="38" r="1.8" fill="#fff" />
          <circle cx="49.5" cy="38" r="1.8" fill="#fff" />
        </svg>
      );
    case 'qqbot':
      return (
        <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
          <ellipse cx="32" cy="24" rx="12" ry="14" fill="#1F2937" />
          <ellipse cx="32" cy="45" rx="15" ry="13" fill="#1F2937" />
          <ellipse cx="32" cy="29" rx="9" ry="10" fill="#fff" />
          <ellipse cx="27.5" cy="22" rx="2.1" ry="2.6" fill="#fff" />
          <ellipse cx="36.5" cy="22" rx="2.1" ry="2.6" fill="#fff" />
          <ellipse cx="27.5" cy="22" rx="1" ry="1.2" fill="#111827" />
          <ellipse cx="36.5" cy="22" rx="1" ry="1.2" fill="#111827" />
          <path fill="#F59E0B" d="M32 26l3.6 2.8L32 31.6l-3.6-2.8z" />
          <path fill="#EF4444" d="M24 41h16v9H24z" />
          <path fill="#F59E0B" d="M22 54h7l-2.8 4.5H21zm20 0h7l1 4.5h-5.2z" />
        </svg>
      );
    case 'onebot':
      return (
        <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
          <circle cx="32" cy="32" r="22" fill="#111827" />
          <circle cx="32" cy="32" r="15" fill="#fff" />
          <circle cx="32" cy="32" r="7" fill="#111827" />
          <path fill="#111827" d="M31 12h2v10h-2zm0 30h2v10h-2zm20-11v2H41v-2zM23 31v2H13v-2z" />
        </svg>
      );
    default:
      return null;
  }
}
