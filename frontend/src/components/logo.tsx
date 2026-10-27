// Логотип ФСП в векторе. Знак и «ФСП» перерисованы по исходному PNG 397×50,
// подпись набрана JetBrains Mono, как в оригинале, и подогнана по ширине строк через textLength.
// Буквы и подпись рисуются currentColor, поэтому логотип работает на светлом и тёмном фоне.
const red = "#ec1d35";
const blue = "#402fff";
const grey = "#c8c9ca";

function Molecule({
  color,
  nodes,
  links,
}: {
  color: string;
  nodes: [number, number][];
  links: [number, number][];
}) {
  return (
    <g fill={color} stroke={color} strokeWidth={2.6}>
      {links.map(([a, b]) => (
        <line
          key={`${a}-${b}`}
          x1={nodes[a][0]}
          y1={nodes[a][1]}
          x2={nodes[b][0]}
          y2={nodes[b][1]}
        />
      ))}
      {nodes.map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={4.4} stroke="none" />
      ))}
    </g>
  );
}

export function FspMark() {
  return (
    <>
      <Molecule
        color={red}
        nodes={[
          [26, 4.5],
          [20, 18.5],
          [32.5, 18.5],
          [47.5, 20],
        ]}
        links={[
          [0, 1],
          [0, 2],
          [2, 3],
        ]}
      />
      <Molecule
        color={grey}
        nodes={[
          [5, 20],
          [16, 30.5],
          [13, 45],
        ]}
        links={[
          [0, 1],
          [1, 2],
        ]}
      />
      <Molecule
        color={blue}
        nodes={[
          [36.5, 30.5],
          [26, 37.5],
          [39, 45],
        ]}
        links={[
          [0, 2],
          [1, 2],
        ]}
      />
    </>
  );
}

export function FspLogo({
  variant = "full",
  className,
}: {
  variant?: "full" | "mark";
  className?: string;
}) {
  if (variant === "mark")
    return (
      <svg
        className={className}
        viewBox="0 0 52 50"
        role="img"
        aria-label="ФСП"
      >
        <FspMark />
      </svg>
    );
  return (
    <svg
      className={className}
      viewBox="0 0 397 50"
      role="img"
      aria-label="ФСП — Федерация спортивного программирования России"
    >
      <FspMark />
      <rect x={56} y={0} width={4} height={50} fill="#e03131" />
      <g fill="currentColor">
        <path
          fillRule="evenodd"
          d="M74 7.5h5.5V11h4.5a7 7 0 0 1 7 7v12.5a7.5 7.5 0 0 1-7.5 7.5h-4V42H74v-4h-4a7 7 0 0 1-7-7V18a7 7 0 0 1 7-7h4ZM74 16.5h-3.5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2H74ZM79.5 16.5v16h3.5a2 2 0 0 0 2-2v-12a2 2 0 0 0-2-2Z"
        />
        <path d="M104 11h9a6.5 6.5 0 0 1 6.5 6.5V18.5H114V17.8a1.3 1.3 0 0 0-1.3-1.3h-8.2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8.2a1.3 1.3 0 0 0 1.3-1.3V30.5h5.5v1.5A6 6 0 0 1 113.5 38H104a7 7 0 0 1-7-7V18a7 7 0 0 1 7-7Z" />
        <path d="M128 11h17a1.5 1.5 0 0 1 1.5 1.5V38H141V16.5h-10.5V38H125V14a3 3 0 0 1 3-3Z" />
      </g>
      <g
        fill="currentColor"
        fontFamily="'JetBrains Mono', ui-monospace, Consolas, monospace"
        fontSize={17.25}
      >
        <text x={158} y={21} textLength={218} lengthAdjust="spacingAndGlyphs">
          федерация спортивного
        </text>
        <text x={158} y={39} textLength={239} lengthAdjust="spacingAndGlyphs">
          программирования России
        </text>
      </g>
    </svg>
  );
}
