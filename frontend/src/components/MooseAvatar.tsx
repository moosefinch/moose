import React, { useCallback } from 'react';

export type AvatarState = 'idle' | 'thinking' | 'talking' | 'success' | 'error' | 'greeting';

interface MooseAvatarProps {
  state?: AvatarState;
  size?: number;
  className?: string;
  onClick?: () => void;
}

const ANTLER_TIP_COLORS: Record<AvatarState, string> = {
  idle: '#9a8872',
  thinking: '#d4b06a',
  talking: '#4a7a65',
  success: '#4a7a65',
  error: '#c45c5c',
  greeting: '#d4b06a',
};

const MooseAvatar: React.FC<MooseAvatarProps> = ({
  state = 'idle',
  size = 200,
  className = '',
  onClick,
}) => {
  const getStateClass = useCallback(() => `mf-${state}`, [state]);
  const tipColor = ANTLER_TIP_COLORS[state];

  return (
    <div
      className={`moose-wrapper ${className}`}
      style={{ width: size, height: size }}
      onClick={onClick}
    >
      <style>{`
        .moose-wrapper {
          position: relative;
          cursor: pointer;
        }
        
        .mf-svg {
          width: 100%;
          height: 100%;
          display: block;
          filter: drop-shadow(0 8px 24px rgba(0, 0, 0, 0.3));
        }

        /* IDLE */
        .mf-idle .body-group {
          animation: idle-breathe 5s ease-in-out infinite;
        }
        .mf-idle .wing-left {
          animation: idle-wing-l 6s ease-in-out infinite;
        }
        .mf-idle .wing-right {
          animation: idle-wing-r 6s ease-in-out infinite;
        }
        .mf-idle .tail-feathers {
          animation: idle-tail 7s ease-in-out infinite;
        }
        
        /* THINKING */
        .mf-thinking .body-group {
          animation: think-alert 2.5s ease-in-out infinite;
        }
        .mf-thinking .wing-left,
        .mf-thinking .wing-right {
          animation: think-wings 0.8s ease-in-out infinite alternate;
        }
        .mf-thinking .ear-left,
        .mf-thinking .ear-right {
          animation: think-ears 1.5s ease-in-out infinite;
        }
        .mf-thinking .glow-ring {
          opacity: 1;
          animation: glow-pulse 2s ease-in-out infinite;
        }
        
        /* TALKING */
        .mf-talking .body-group {
          animation: talk-engage 0.6s ease-in-out infinite;
        }
        .mf-talking .wing-left {
          animation: talk-wing-l 1s ease-in-out infinite;
        }
        .mf-talking .wing-right {
          animation: talk-wing-r 1s ease-in-out infinite;
        }
        .mf-talking .beak {
          animation: talk-beak 0.35s ease-in-out infinite;
        }
        
        /* SUCCESS */
        .mf-success .body-group {
          animation: success-proud 0.8s cubic-bezier(0.34, 1.2, 0.64, 1) infinite;
        }
        .mf-success .wing-left {
          animation: success-wing-l 0.6s ease-out forwards;
        }
        .mf-success .wing-right {
          animation: success-wing-r 0.6s ease-out forwards;
        }
        .mf-success .crown-glow {
          opacity: 1;
          animation: crown-shine 1s ease-in-out infinite;
        }
        
        /* ERROR */
        .mf-error .body-group {
          animation: error-wary 0.4s ease-in-out infinite;
        }
        .mf-error .wing-left,
        .mf-error .wing-right {
          animation: error-wings 0.5s ease-out forwards;
        }
        .mf-error .ear-left,
        .mf-error .ear-right {
          animation: error-ears 0.4s ease-out forwards;
        }
        
        /* GREETING */
        .mf-greeting .body-group {
          animation: greet-nod 0.8s ease-in-out infinite;
        }
        .mf-greeting .wing-right {
          animation: greet-wing 0.5s ease-in-out infinite alternate;
          transform-origin: 75% 70%;
        }

        /* KEYFRAMES */
        @keyframes idle-breathe {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-2px); }
        }
        
        @keyframes idle-wing-l {
          0%, 100% { transform: rotate(0deg); }
          50% { transform: rotate(-2deg); }
        }
        
        @keyframes idle-wing-r {
          0%, 100% { transform: rotate(0deg); }
          50% { transform: rotate(2deg); }
        }
        
        @keyframes idle-tail {
          0%, 100% { transform: rotate(0deg); }
          50% { transform: rotate(1deg); }
        }
        
        @keyframes think-alert {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-3px); }
        }
        
        @keyframes think-wings {
          0% { transform: translateY(0); }
          100% { transform: translateY(-4px); }
        }
        
        @keyframes think-ears {
          0%, 100% { transform: rotate(0deg); }
          50% { transform: rotate(3deg); }
        }
        
        @keyframes glow-pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.6; }
        }
        
        @keyframes talk-engage {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-2px); }
        }
        
        @keyframes talk-wing-l {
          0%, 100% { transform: rotate(0deg); }
          50% { transform: rotate(-5deg); }
        }
        
        @keyframes talk-wing-r {
          0%, 100% { transform: rotate(0deg); }
          50% { transform: rotate(5deg); }
        }
        
        @keyframes talk-beak {
          0%, 100% { transform: scaleY(1); }
          50% { transform: scaleY(0.85); }
        }
        
        @keyframes success-proud {
          0%, 100% { transform: translateY(0) scale(1); }
          50% { transform: translateY(-6px) scale(1.01); }
        }
        
        @keyframes success-wing-l {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(-18deg) translateY(-5px); }
        }
        
        @keyframes success-wing-r {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(18deg) translateY(-5px); }
        }
        
        @keyframes crown-shine {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 0.9; }
        }
        
        @keyframes error-wary {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-2px); }
          75% { transform: translateX(2px); }
        }
        
        @keyframes error-wings {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(5deg) translateY(3px); }
        }
        
        @keyframes error-ears {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(-8deg); }
        }
        
        @keyframes greet-nod {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          50% { transform: translateY(-4px) rotate(1deg); }
        }
        
        @keyframes greet-wing {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(10deg); }
        }
        
        .glow-ring { opacity: 0; transition: opacity 0.3s; }
        .crown-glow { opacity: 0; transition: opacity 0.3s; }

        .antler-tip {
          transition: fill 0.6s ease, filter 0.6s ease;
        }

        .mf-idle .antler-tip {
          filter: drop-shadow(0 0 2px currentColor);
        }

        .mf-thinking .antler-tip {
          animation: tip-pulse 1.5s ease-in-out infinite;
        }

        .mf-talking .antler-tip {
          animation: tip-pulse 0.8s ease-in-out infinite;
        }

        .mf-success .antler-tip {
          animation: tip-pulse 1s ease-in-out infinite;
        }

        .mf-error .antler-tip {
          animation: tip-flash 0.4s ease-in-out infinite;
        }

        .mf-greeting .antler-tip {
          animation: tip-pulse 1.2s ease-in-out infinite;
        }

        @keyframes tip-pulse {
          0%, 100% { opacity: 0.8; }
          50% { opacity: 1; }
        }

        @keyframes tip-flash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>

      <svg viewBox="0 0 200 200" className={`mf-svg ${getStateClass()}`}>
        <defs>
          <linearGradient id="furDark" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#5c4a3d"/>
            <stop offset="100%" stopColor="#3d3029"/>
          </linearGradient>
          
          <linearGradient id="furMid" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#8b7355"/>
            <stop offset="50%" stopColor="#6d5a47"/>
            <stop offset="100%" stopColor="#4a3d32"/>
          </linearGradient>
          
          <linearGradient id="furLight" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#a69076"/>
            <stop offset="100%" stopColor="#8b7355"/>
          </linearGradient>
          
          <linearGradient id="furChest" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#d4c4a8"/>
            <stop offset="100%" stopColor="#b8a88c"/>
          </linearGradient>
          
          <linearGradient id="antler" x1="50%" y1="100%" x2="50%" y2="0%">
            <stop offset="0%" stopColor="#6b5d4d"/>
            <stop offset="30%" stopColor="#9c8b74"/>
            <stop offset="70%" stopColor="#c4b59c"/>
            <stop offset="100%" stopColor="#e0d5c3"/>
          </linearGradient>
          
          <linearGradient id="wingPrimary" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#2d4a3e"/>
            <stop offset="40%" stopColor="#1f3830"/>
            <stop offset="100%" stopColor="#162822"/>
          </linearGradient>
          
          <linearGradient id="wingSecondary" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#4a6b5a"/>
            <stop offset="50%" stopColor="#3d5a4a"/>
            <stop offset="100%" stopColor="#2d4a3e"/>
          </linearGradient>
          
          <linearGradient id="wingAccent" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#c9a962"/>
            <stop offset="50%" stopColor="#a68b4b"/>
            <stop offset="100%" stopColor="#8b7340"/>
          </linearGradient>
          
          <radialGradient id="eyeOuter" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#4a3d28"/>
            <stop offset="100%" stopColor="#2a1f14"/>
          </radialGradient>
          
          <radialGradient id="eyeInner" cx="30%" cy="30%" r="60%">
            <stop offset="0%" stopColor="#c9a962"/>
            <stop offset="60%" stopColor="#8b6b2a"/>
            <stop offset="100%" stopColor="#5a4420"/>
          </radialGradient>
          
          <linearGradient id="beak" x1="50%" y1="0%" x2="50%" y2="100%">
            <stop offset="0%" stopColor="#4a4038"/>
            <stop offset="100%" stopColor="#2d2620"/>
          </linearGradient>
          
          <radialGradient id="glowGold" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#c9a962" stopOpacity="0.4"/>
            <stop offset="100%" stopColor="#c9a962" stopOpacity="0"/>
          </radialGradient>
          
          <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>

          <filter id="tipGlow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="4" result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        
        <circle className="glow-ring" cx="100" cy="95" r="75" fill="url(#glowGold)"/>
        <ellipse className="crown-glow" cx="100" cy="35" rx="30" ry="20" fill="url(#glowGold)"/>
        
        <g className="body-group">
          {/* Tail */}
          <g className="tail-feathers" style={{ transformOrigin: '100px 160px' }}>
            <path d="M 85 155 Q 70 170 65 185 Q 80 175 90 165 Z" fill="url(#wingPrimary)"/>
            <path d="M 95 158 Q 90 175 88 192 Q 98 178 100 165 Z" fill="url(#wingSecondary)"/>
            <path d="M 105 158 Q 110 175 112 192 Q 102 178 100 165 Z" fill="url(#wingSecondary)"/>
            <path d="M 115 155 Q 130 170 135 185 Q 120 175 110 165 Z" fill="url(#wingPrimary)"/>
          </g>
          
          {/* Wings */}
          <g className="wing-left" style={{ transformOrigin: '65px 100px' }}>
            <path d="M 62 90 Q 30 75 15 55 Q 18 70 22 82 Q 8 72 5 85 Q 15 95 25 98 Q 10 100 12 115 Q 25 112 35 108 Q 22 120 30 130 Q 42 122 52 115 Q 45 130 55 138 L 62 115 Z" fill="url(#wingPrimary)"/>
            <path d="M 60 95 Q 40 85 30 75 Q 35 88 40 95 Q 28 92 25 102 Q 38 102 48 100 Q 38 110 45 118 L 58 108 Z" fill="url(#wingSecondary)"/>
            <path d="M 55 92 Q 38 88 28 82" stroke="url(#wingAccent)" strokeWidth="3" fill="none" strokeLinecap="round"/>
            <path d="M 52 102 Q 35 100 25 98" stroke="url(#wingAccent)" strokeWidth="2" fill="none" strokeLinecap="round" opacity="0.7"/>
          </g>
          
          <g className="wing-right" style={{ transformOrigin: '135px 100px' }}>
            <path d="M 138 90 Q 170 75 185 55 Q 182 70 178 82 Q 192 72 195 85 Q 185 95 175 98 Q 190 100 188 115 Q 175 112 165 108 Q 178 120 170 130 Q 158 122 148 115 Q 155 130 145 138 L 138 115 Z" fill="url(#wingPrimary)"/>
            <path d="M 140 95 Q 160 85 170 75 Q 165 88 160 95 Q 172 92 175 102 Q 162 102 152 100 Q 162 110 155 118 L 142 108 Z" fill="url(#wingSecondary)"/>
            <path d="M 145 92 Q 162 88 172 82" stroke="url(#wingAccent)" strokeWidth="3" fill="none" strokeLinecap="round"/>
            <path d="M 148 102 Q 165 100 175 98" stroke="url(#wingAccent)" strokeWidth="2" fill="none" strokeLinecap="round" opacity="0.7"/>
          </g>
          
          {/* Body */}
          <ellipse cx="100" cy="120" rx="40" ry="42" fill="url(#furMid)"/>
          <ellipse cx="100" cy="130" rx="25" ry="28" fill="url(#furChest)"/>
          <ellipse cx="100" cy="138" rx="18" ry="18" fill="url(#furLight)" opacity="0.5"/>
          
          <path d="M 88 118 Q 92 128 88 140" stroke="#c4b49a" strokeWidth="1" fill="none" opacity="0.4"/>
          <path d="M 100 115 Q 100 130 100 145" stroke="#c4b49a" strokeWidth="1" fill="none" opacity="0.4"/>
          <path d="M 112 118 Q 108 128 112 140" stroke="#c4b49a" strokeWidth="1" fill="none" opacity="0.4"/>
          
          {/* Neck & Head */}
          <ellipse cx="100" cy="85" rx="28" ry="22" fill="url(#furMid)"/>
          <ellipse cx="100" cy="62" rx="30" ry="28" fill="url(#furLight)"/>
          <path d="M 75 55 Q 85 50 100 48 Q 115 50 125 55 Q 120 62 100 65 Q 80 62 75 55 Z" fill="url(#furMid)" opacity="0.6"/>
          
          {/* Ears */}
          <g className="ear-left" style={{ transformOrigin: '72px 42px' }}>
            <path d="M 72 48 Q 60 35 55 25 Q 52 35 58 45 Q 65 50 72 48 Z" fill="url(#furMid)"/>
            <path d="M 68 45 Q 62 38 60 32" stroke="#d4c4a8" strokeWidth="2" fill="none" opacity="0.5"/>
          </g>
          <g className="ear-right" style={{ transformOrigin: '128px 42px' }}>
            <path d="M 128 48 Q 140 35 145 25 Q 148 35 142 45 Q 135 50 128 48 Z" fill="url(#furMid)"/>
            <path d="M 132 45 Q 138 38 140 32" stroke="#d4c4a8" strokeWidth="2" fill="none" opacity="0.5"/>
          </g>
          
          {/* Antlers */}
          <g filter="url(#softGlow)">
            <path d="M 78 45 Q 72 30 65 15 M 72 30 Q 60 28 52 22 M 72 30 Q 65 22 58 18 M 68 38 Q 55 38 45 35 M 68 38 Q 58 32 50 28" fill="none" stroke="url(#antler)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/>

            <path d="M 122 45 Q 128 30 135 15 M 128 30 Q 140 28 148 22 M 128 30 Q 135 22 142 18 M 132 38 Q 145 38 155 35 M 132 38 Q 142 32 150 28" fill="none" stroke="url(#antler)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/>
          </g>

          {/* Antler tips — glow with status color */}
          <g filter="url(#tipGlow)">
            <circle className="antler-tip" cx="65" cy="15" r="3" fill={tipColor}/>
            <circle className="antler-tip" cx="52" cy="22" r="2.5" fill={tipColor}/>
            <circle className="antler-tip" cx="58" cy="18" r="2.5" fill={tipColor}/>
            <circle className="antler-tip" cx="45" cy="35" r="2.5" fill={tipColor}/>
            <circle className="antler-tip" cx="50" cy="28" r="2.5" fill={tipColor}/>

            <circle className="antler-tip" cx="135" cy="15" r="3" fill={tipColor}/>
            <circle className="antler-tip" cx="148" cy="22" r="2.5" fill={tipColor}/>
            <circle className="antler-tip" cx="142" cy="18" r="2.5" fill={tipColor}/>
            <circle className="antler-tip" cx="155" cy="35" r="2.5" fill={tipColor}/>
            <circle className="antler-tip" cx="150" cy="28" r="2.5" fill={tipColor}/>
          </g>
          
          {/* Eyes */}
          <g className="eyes">
            <ellipse cx="85" cy="60" rx="8" ry="9" fill="url(#eyeOuter)"/>
            <ellipse cx="85" cy="60" rx="5" ry="6" fill="url(#eyeInner)"/>
            <ellipse cx="85" cy="60" rx="2.5" ry="3" fill="#1a1408"/>
            <circle cx="83" cy="58" r="1.5" fill="#fff" opacity="0.8"/>
            
            <ellipse cx="115" cy="60" rx="8" ry="9" fill="url(#eyeOuter)"/>
            <ellipse cx="115" cy="60" rx="5" ry="6" fill="url(#eyeInner)"/>
            <ellipse cx="115" cy="60" rx="2.5" ry="3" fill="#1a1408"/>
            <circle cx="113" cy="58" r="1.5" fill="#fff" opacity="0.8"/>
          </g>
          
          <path d="M 78 52 Q 85 50 92 52" stroke="#4a3d32" strokeWidth="1.5" fill="none" opacity="0.5"/>
          <path d="M 108 52 Q 115 50 122 52" stroke="#4a3d32" strokeWidth="1.5" fill="none" opacity="0.5"/>
          
          {/* Beak */}
          <g className="beak" style={{ transformOrigin: '100px 72px' }}>
            <path d="M 95 68 Q 100 65 105 68 L 103 75 Q 100 78 97 75 Z" fill="url(#beak)"/>
            <ellipse cx="100" cy="70" rx="3" ry="2" fill="#1a1408" opacity="0.8"/>
            <ellipse cx="98" cy="68" rx="1.5" ry="1" fill="#5a4a3a" opacity="0.5"/>
          </g>
          
          <path d="M 94 77 Q 100 80 106 77" stroke="#4a3d32" strokeWidth="1" fill="none" opacity="0.4"/>
          
          {/* Feet */}
          <ellipse cx="85" cy="162" rx="8" ry="4" fill="#3d3029"/>
          <ellipse cx="115" cy="162" rx="8" ry="4" fill="#3d3029"/>
        </g>
      </svg>
    </div>
  );
};

export default MooseAvatar;
