import React from 'react';
import { Image, FileText, Search } from 'lucide-react';

interface GradientMenuProps {
  onPhotoUpload?: () => void;
  onPdfUpload?: () => void;
  onWebSearch?: () => void;
  hasPhoto?: boolean;
  hasPdf?: boolean;
}

export default function GradientMenu({ 
  onPhotoUpload, 
  onPdfUpload, 
  onWebSearch,
  hasPhoto = false,
  hasPdf = false
}: GradientMenuProps) {
  const menuItems = [
    { 
      title: 'Photo', 
      icon: <Image size={24} />, 
      gradientFrom: '#38bdf8', 
      gradientTo: '#3b82f6',
      onClick: onPhotoUpload,
      disabled: hasPhoto,
      disabledMessage: "Only 1 photo allowed per session"
    },
    { 
      title: 'PDF', 
      icon: <FileText size={24} />, 
      gradientFrom: '#818cf8', 
      gradientTo: '#4f46e5',
      onClick: onPdfUpload,
      disabled: hasPdf,
      disabledMessage: "Only 1 PDF allowed per session"
    },
    { 
      title: 'Browser', 
      icon: <Search size={24} />, 
      gradientFrom: '#2dd4bf', 
      gradientTo: '#0ea5e9',
      onClick: onWebSearch,
      disabled: false
    }
  ];

  return (
    <div className="flex items-center">
      <ul className="flex gap-3">
        {menuItems.map(({ title, icon, gradientFrom, gradientTo, onClick, disabled, disabledMessage }, idx) => (
          <li
            key={idx}
            onClick={disabled ? undefined : onClick}
            style={{ 
              '--gradient-from': gradientFrom, 
              '--gradient-to': gradientTo 
            } as React.CSSProperties}
            className={`
              relative w-9 h-9 backdrop-blur-md rounded-xl flex items-center justify-center transition-all duration-500 border border-white/10
              ${disabled 
                ? "bg-white/[0.02] opacity-30 cursor-not-allowed group/disabled overflow-visible" 
                : "bg-white/5 hover:w-28 hover:bg-white/10 group cursor-pointer"
              }
            `}
          >
            {/* Disabled Tooltip */}
            {disabled && (
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-black/90 text-white text-[9px] font-bold uppercase tracking-widest whitespace-nowrap rounded-lg opacity-0 transition-opacity pointer-events-none group-hover/disabled:opacity-100 z-50 border border-white/10 shadow-2xl">
                {disabledMessage}
              </div>
            )}

            {/* Gradient background on hover */}
            {!disabled && (
              <span className="absolute inset-0 rounded-xl bg-[linear-gradient(45deg,var(--gradient-from),var(--gradient-to))] opacity-0 transition-all duration-500 group-hover:opacity-100"></span>
            )}
            
            {/* Blur glow */}
            {!disabled && (
              <span className="absolute top-[5px] inset-x-0 h-full rounded-xl bg-[linear-gradient(45deg,var(--gradient-from),var(--gradient-to))] blur-[10px] opacity-0 -z-10 transition-all duration-500 group-hover:opacity-40"></span>
            )}

            {/* Icon */}
            <span className={`relative z-10 transition-all duration-300 ${!disabled && "group-hover:scale-0 group-hover:opacity-0"}`}>
              <span className={`${disabled ? "text-white/20" : "text-white/40 group-hover:text-white"} transition-colors`}>
                {icon}
              </span>
            </span>

            {/* Title */}
            {!disabled && (
              <span className="absolute text-white uppercase tracking-[0.2em] text-[10px] font-bold transition-all duration-500 scale-0 group-hover:scale-100 opacity-0 group-hover:opacity-100">
                {title}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
