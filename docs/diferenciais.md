# Por que o PyMice Web não é apenas mais uma ferramenta de tracking

## Posicionamento

O PyMice Web não compete com soluções genéricas de *pose estimation* (DeepLabCut, SLEAP, DeepPoseKit). Ele ocupa um nicho complementar: **análise etológica de roedores em arenas controladas, com fluxo fechado do vídeo bruto às métricas**, exposto por uma interface web.

A escolha de projeto é deliberada — em vez de oferecer uma ferramenta generalista de marcação de keypoints, o sistema parte de um detector pré-treinado de animal único (centroide via YOLO) e investe na camada que normalmente fica fora do escopo dessas ferramentas: definição interativa de ROIs, agregação etológica, exportação reprodutível e visualização imediata.

## Diferenciais técnicos

### 1. Zero rotulação manual
DeepLabCut exige um ciclo de rotulação supervisionada (tipicamente centenas de frames por experimento), treino e refinamento iterativo. O PyMice Web usa YOLO pré-treinado para detecção de animal único — o usuário carrega o vídeo, desenha ROIs e roda. O custo de entrada é minutos, não dias.

### 2. Detecção em duas camadas
A pipeline executa YOLO como detector primário e cai em **subtração de fundo + template matching** quando o YOLO falha. Cada frame registra o método utilizado (`detection_method`), permitindo auditoria posterior. Em vídeos com iluminação variável ou oclusão parcial, a redundância reduz lacunas no traço — algo que, em DLC, costuma exigir interpolação manual ou re-treino.

### 3. ROIs como cidadãos de primeira classe
Retângulo, círculo e polígono são desenhados sobre o vídeo (React-Konva) e salvos como **templates reutilizáveis** entre sessões. A pertinência por ROI é calculada por frame e exportada junto com o traço — não é uma análise *post-hoc* separada. Em fluxos baseados em DLC, ROIs geralmente são definidas em scripts à parte (matplotlib, shapely), sem padronização entre experimentos.

### 4. Estatísticas robustas por padrão
A velocidade frame-a-frame é filtrada por **Mediana + k·MAD**, com fallback para percentis quando o MAD colapsa em dados quantizados ou inflados em zero. Isso evita que *jitter* de detecção contamine métricas de atividade — algo que tipicamente exige pós-processamento manual em fluxos baseados em DLC.

### 5. Visualização tunada para o domínio
Heatmaps usam **Power Normalization (γ=0.4)** para preservar a visibilidade de regiões de baixa ocupação ao lado de *hotspots*. Trajetórias são configuráveis (cor, espessura, opacidade) e há abas dedicadas para Open Field e análise etológica. Em DLC, a visualização é responsabilidade do usuário.

### 6. Timestamps via ffmpeg, não via índice de frame
Os timestamps exportados vêm do *container* do vídeo (ffmpeg/ffprobe), não da multiplicação `frame_idx / fps`. Em vídeos com VFR ou frames descartados, isso evita deriva temporal silenciosa.

### 7. *Stack* web, não *desktop*
O pesquisador acessa o sistema pelo navegador — sem instalação de pacote Python, ambiente Conda ou configuração de GPU do lado do usuário final. O backend FastAPI pode rodar em uma máquina central com GPU e atender múltiplos usuários simultaneamente.

### 8. Tracking ao vivo, gravação e closed-loop em uma única aba
A aba **Experiment Recording** (`pages/ExperimentRecordingTab.tsx`) consome a câmera USB diretamente, desenha ROIs sobre o frame ao vivo (componente compartilhado `ROICanvas`), roda YOLO frame-a-frame e grava simultaneamente o **vídeo bruto** e um **`tracking.jsonl`** sincronizado por `frame_idx`. Eventos de ROI (`roi_entry`, `roi_exit`) e disparos são publicados em um **canal WebSocket** (`/api/experiment/events`); regras de **trigger** declarativas (cooldown, min_dwell) podem disparar **ações em hardware** — Arduino/ESP32 via USB serial, ou ESP32 via HTTP em LAN. Tudo em um único processo FastAPI, com a porta serial mantida aberta entre disparos para evitar reset-on-open do Arduino.

## Quando preferir DeepLabCut (ou similar)

O escopo é deliberadamente estreito. O PyMice Web **não substitui** *pose estimation* quando:

- O experimento exige **múltiplos *keypoints*** (postura corporal, ângulo de cabeça, *rearing*, *freezing*, *grooming* via *keypoints*).
- O alvo é uma **espécie ou objeto fora da distribuição** do YOLO pré-treinado e não há possibilidade de *fine-tuning*.
- A análise depende de **cinemática fina** (segmentação articular, marcha, simetria de membros).

Nesses casos, DLC/SLEAP — ou o suporte opcional a **SAM3** já presente no backend para segmentação assistida — são as ferramentas certas.

## Resumo

PyMice Web é um **pipeline etológico opinativo** para roedores em arena, não um *framework* genérico de *tracking*. A diferenciação vem da integração — ROI + detecção redundante + estatísticas robustas + visualização específica + exportação padronizada — em um fluxo único, operável por navegador, sem etapa de rotulação.
