import { useState } from "react";

export function MorphButton({
  label = "Login / Sign Up",
  onClick,
}: {
  label?: string;
  onClick?: () => void;
}) {
  const [clicked, setClicked] = useState(false);
  
  const handleClick = () => {
    setClicked(true);
    if (onClick) onClick();
  };

  return (
    <button
      onClick={handleClick}
      disabled={clicked}
      className="
        relative w-12 h-12 sm:w-14 sm:h-14
        bg-white/5 backdrop-blur-md rounded-full
        flex items-center justify-center
        transition-all duration-500
        hover:w-[180px] sm:hover:w-[240px]
        hover:bg-white/5
        group cursor-pointer
        border border-white/20
        hover:border-[#c5a059]
        hover:shadow-[0_0_25px_rgba(197,160,89,0.5)]
        disabled:pointer-events-none
        overflow-hidden
      "
    >
      {/* Arrow — visible by default, disappears on hover */}
      <span className="absolute inset-0 transition-all duration-500 group-hover:scale-0 group-hover:opacity-0 flex items-center justify-center">
        <span className="text-white/60 text-2xl font-light">→</span>
      </span>
      {/* Label — hidden by default, appears on hover */}
      <span className="absolute text-white tracking-[0.2em] text-[10px] sm:text-xs font-bold transition-all duration-500 scale-0 opacity-0 group-hover:scale-100 group-hover:opacity-100 whitespace-nowrap uppercase">
        {label}
      </span>
    </button>
  );
}
