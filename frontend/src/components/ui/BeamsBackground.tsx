"use client";

import { useEffect, useRef, ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "../../lib/utils";

interface Beam {
  x: number;
  y: number;
  width: number;
  length: number;
  angle: number;
  speed: number;
  opacity: number;
  hue: number;
  pulse: number;
  pulseSpeed: number;
}

interface BeamsBackgroundProps {
  children?: ReactNode;
  className?: string;
  active?: boolean;
}

/**
 * A premium, high-performance 'Beam Light Background' component using HTML5 Canvas.
 * Features animated vertical/diagonal beams with deep space aesthetic and blur glow.
 */
export function BeamsBackground({ children, className, active = true }: BeamsBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const beamsRef = useRef<Beam[]>([]);
  const animationFrameRef = useRef<number>(0);

  // Logical helper to create a beam with randomized properties
  const createBeam = (width: number, height: number): Beam => ({
    x: Math.random() * width * 1.5 - width * 0.25,
    y: Math.random() * height * 1.5 - height * 0.25,
    width: 30 + Math.random() * 60,
    length: height * 2.5,
    angle: -35 + Math.random() * 10,
    speed: 0.4 + Math.random() * 0.6,
    opacity: 0.2 + Math.random() * 0.2,
    hue: 220 + Math.random() * 20, // Vibrant Blue/Cyan/Purple range
    pulse: Math.random() * Math.PI * 2,
    pulseSpeed: 0.03 + Math.random() * 0.04,
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !active) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // 🚀 Persistence Fix: Initialize beams ONLY once if they don't exist
    if (beamsRef.current.length === 0) {
      const isMobile = window.innerWidth < 768;
      beamsRef.current = Array.from({ length: isMobile ? 10 : 15 }, () => 
        createBeam(window.innerWidth, window.innerHeight)
      );
    }

    const updateCanvasSize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      // Use client dimensions to avoid scrollbar jitter
      const width = window.innerWidth;
      const height = window.innerHeight;
      
      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.setTransform(1, 0, 0, 1, 0, 0); // Reset transform before scaling
        ctx.scale(dpr, dpr);
      }
    };

    updateCanvasSize();
    window.addEventListener("resize", updateCanvasSize);

    const animate = () => {
      if (!ctx || !canvas) return;
      
      // Use raw width/height to bypass any current scales when clearing
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.restore();
      
      beamsRef.current.forEach((beam) => {
        beam.y -= beam.speed;
        beam.pulse += beam.pulseSpeed;
        
        // Loop vertically
        if (beam.y + beam.length < -400) {
          beam.y = window.innerHeight + 200;
        }
        
        ctx.save();
        ctx.translate(beam.x, beam.y);
        ctx.rotate((beam.angle * Math.PI) / 180);
        
        const grad = ctx.createLinearGradient(0, 0, 0, beam.length);
        const alpha = beam.opacity * (0.9 + Math.sin(beam.pulse) * 0.1);
        
        grad.addColorStop(0, `hsla(${beam.hue}, 60%, 55%, 0)`);
        grad.addColorStop(0.5, `hsla(${beam.hue}, 60%, 55%, ${alpha})`);
        grad.addColorStop(1, `hsla(${beam.hue}, 60%, 55%, 0)`);
        
        ctx.fillStyle = grad;
        ctx.fillRect(-beam.width / 2, 0, beam.width, beam.length);
        ctx.restore();
      });
      
      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener("resize", updateCanvasSize);
      cancelAnimationFrame(animationFrameRef.current);
    };
  }, [active]);

  return (
    <div className={cn("relative w-full min-h-screen bg-black overflow-hidden", className)}>
      {/* Background Canvas Layer */}
      <canvas 
        ref={canvasRef} 
        className="fixed inset-0 z-0 pointer-events-none transition-opacity duration-1000" 
        style={{ filter: 'blur(20px)' }} 
      />

      {/* Pulsing Ambient Glow Layer */}
      <motion.div 
        className="fixed inset-0 z-0 bg-white/5 pointer-events-none" 
        animate={{ opacity: [0.03, 0.08, 0.03] }} 
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }} 
      />

      {/* Page Content */}
      <div className="relative z-10 w-full h-full">
        {children}
      </div>
    </div>
  );
}
