'use client';
import { Siren } from 'lucide-react';

interface SOSButtonProps {
  onPress: () => void;
  isLoading?: boolean;
  isSuccess?: boolean;
}

export default function SOSButton({ onPress, isLoading, isSuccess }: SOSButtonProps) {
  return (
    <div className="relative flex items-center justify-center">
      {/* Pulse rings */}
      {!isSuccess && !isLoading && (
        <>
          <span className="absolute w-48 h-48 rounded-full bg-red-500/20 animate-ping" style={{ animationDuration: '2s' }} />
          <span className="absolute w-40 h-40 rounded-full bg-red-500/15 animate-ping" style={{ animationDuration: '2s', animationDelay: '0.5s' }} />
        </>
      )}
      
      <button
        onClick={onPress}
        disabled={isLoading || isSuccess}
        className={`
          relative w-36 h-36 rounded-full font-black text-white text-2xl tracking-widest
          shadow-2xl transition-all duration-300 select-none
          focus:outline-none focus:ring-4 focus:ring-red-500/50
          ${isSuccess 
            ? 'bg-gradient-to-br from-green-500 to-green-700 shadow-green-500/40 scale-95' 
            : isLoading 
              ? 'bg-gradient-to-br from-red-400 to-red-600 opacity-70 cursor-not-allowed scale-95'
              : 'bg-gradient-to-br from-red-500 to-red-700 hover:from-red-400 hover:to-red-600 shadow-red-500/50 hover:scale-105 active:scale-95 cursor-pointer'
          }
        `}
      >
        {isLoading ? (
          <div className="flex flex-col items-center gap-1">
            <div className="w-7 h-7 border-4 border-white/30 border-t-white rounded-full animate-spin" />
            <span className="text-xs font-bold opacity-80">ENVOI...</span>
          </div>
        ) : isSuccess ? (
          <div className="flex flex-col items-center gap-1">
            <span className="text-3xl">✓</span>
            <span className="text-xs font-bold">ENVOYÉ</span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1">
            <Siren className="w-8 h-8" />
            <span>SOS</span>
          </div>
        )}
      </button>
    </div>
  );
}
