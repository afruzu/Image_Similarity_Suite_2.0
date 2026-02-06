# Image Similarity Suite 2.0

## 🎯 Scopo del Programma

**Image Similarity Suite 2.0** è un'applicazione desktop per l'analisi, rilevamento e gestione di **duplicati e file similari** (foto e video) su disco. Perfetta per:

- 📸 **Pulizia di librerie fotografiche** (eliminare foto duplicate/simili)
- 🎬 **Gestione collezioni video** (trovare versioni diverse dello stesso video)
- 💾 **Recupero spazio su disco** (identificare e eliminare duplicati)
- 🔍 **Analisi visiva avanzata** (con supporto sia a hashing percettivo che analisi di keyframe)

**Caratteristiche principali:**
- ✅ Analisi di cartelle complete (foto + video misti)
- ✅ 3 fasi di analisi intelligente e parallela
- ✅ Interfaccia grafica interattiva per decidere su ogni duplicato
- ✅ Impostazioni configurabili e salvate
- ✅ Logging completo di tutte le operazioni
- ✅ Support per foto corrotte/video non accessibili (skip intelligente)

---

## 📋 Requisiti di Sistema

- **Python 3.10+** (testato su 3.12)
- **PySide6** (Qt6 per Python)
- **OpenCV (cv2)** 4.13+
- **NumPy** 2.3+
- **Pillow (PIL)** per elaborazione immagini

**Formati supportati:**
- Foto: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.gif`, `.webp`, `.tiff`
- Video: `.mp4`, `.mov`, `.mkv`, `.avi`, `.flv`, `.wmv`

---

## 🚀 Avvio Rapido

### 1. Installazione Dipendenze
```bash
pip install PySide6 opencv-python numpy pillow
```

### 2. Esecuzione
```bash
python main.py
```

L'interfaccia si aprirà immediatamente. Non è richiesta compilazione o setup aggiuntivo.

---

## 🎮 Guida Operativa

### Flusso Principale

#### **Step 1: Seleziona Cartella**
1. Clicca il pulsante **SCANSIONE** (rosso, in alto a sinistra)
2. Seleziona la cartella che vuoi analizzare
3. Il programma comincia automaticamente l'analisi in 3 fasi

#### **Step 2: Monitora il Progresso**
L'interfaccia mostra **3 barre di progresso colorate**:
- 🔴 **P1 (Rosso)**: Fase 1 - Ricerca duplicati MD5 (100% affidabili)
- 🔵 **P2 (Blu)**: Fase 2 - Analisi visiva immagini (pHash)
- 🟠 **P3 (Arancione)**: Fase 3 - Confronto video (keyframe matching)

#### **Step 3: Revisiona i Risultati**
Mentre le fasi progrediscono, le coppie duplicate/simili appaiono come **carte** nella galleria centrale.

**Ogni carta mostra:**
- Due thumbnail fianco a fianco
- Score di similarità (0-100%)
- Tipo di file (FOTO/VIDEO)
- Dimensioni, risoluzione, durata video
- Pulsanti di decisione
 - Pulsante **KEYFRAMES** (video): apre una finestra con i keyframe estratti; cliccando su una miniatura o sul pulsante "Apri Zoom Coppia" si apre una vista ingrandita e navigabile dei keyframe per esaminare i dettagli (la card viene automaticamente messa a fuoco quando si apre la finestra).

#### **Step 4: Prendi Decisioni**
Per ogni coppia duplicata, scegli una delle 4 azioni:

| Pulsante | Hotkey | Effetto |
|----------|--------|--------|
| **TIENI A** | `A` | Mantieni file A, segna B come duplicato |
| **TIENI B** | `B` | Mantieni file B, segna A come duplicato |
| **DIVERSE** | `D` | Non sono duplicati, skippa questa coppia |
| **ELIMINA ENTRAMBI** | `E` | Elimina sia A che B (uso raro) |

---

## ⌨️ Hotkey e Scorciatoie

### Navigazione Carte
| Tasto | Effetto |
|-------|--------|
| `Freccia Su / Giù` | Scorri tra le carte della galleria |
| `Pagina Su / Pagina Giù` | Scroll rapido |

### Modalità Visualizzazione (Foto)
| Tasto | Effetto |
|-------|--------|
| `1` | Zoom Fit (adatta tutta l'immagine) |
| `2` | Zoom 150% |
| `3` | Zoom 1:1 (pixel perfetto) |
| `4` | Mappa Differenze (grayscale diff overlay) |
| `+` | Cicla tra le 4 modalità |
| `-` | Cicla all'indietro |
| `Space` | Reset posizione prima immagine |
| `ESC` | Reset posizione entrambe |

### Zoom Keyframes (Video)
| Tasto | Effetto |
|------:|--------|
| `Freccia Su / Freccia Sinistra` | In Keyframes Zoom: vai al frame/coppia precedente |
| `Freccia Giù / Freccia Destra` | In Keyframes Zoom: vai al frame/coppia successiva |
| Click su miniatura | Apre il Keyframes Zoom sulla coppia selezionata |

### Decisioni Rapide
| Tasto | Effetto |
|-------|--------|
| `A` | Tieni file A |
| `B` | Tieni file B |
| `D` | Diversi (skippa questa coppia) |
| `E` | Elimina entrambi |

### Menu Contestuale
Clic destro su una carta apre un menu con tutte le opzioni sopra elencate.

---

## ⚙️ Impostazioni Configurabili

Clicca **IMPOSTAZIONI** (pulsante arancione in alto) per modificare i parametri di analisi.

### Fase 1: MD5 (Duplicati Certi)
*Automatica, nessuna configurazione.*
- Scansiona tutti i file per hash MD5
- I duplicati esatti vengono **spostati** in cartella `duplicati_certi/`
- Affidabilità: **100%**

### Fase 2: pHash (Immagini Simili)
*Automatica, nessuna configurazione.*
- Usa hashing percettivo per foto simili (non identiche)
- Soglia di default: distanza < 12
- Perfetto per foto duplicate leggermente modificate

### Fase 3: Video (Confronto Keyframe)
**Parametri configurabili:**

| Parametro | Default | Range | Descrizione |
|-----------|---------|-------|-------------|
| **Tolleranza durata** | 2% | 0-100% | Video con durata entro ±X% sono candidati |
| **Tolleranza risoluzione** | 5% | 0-100% | Video con risoluzione entro ±X% sono candidati |
| **Soglia score** | 60% | 0-100% | Match video richiede ≥ X% di similarità |
| **Max worker** | 4 | 1-64 | Thread paralleli per confronti video |
| **Soglia scene** | 30 | 0-255 | Sensibilità rilevamento cambio scena (0=bassa, 255=alta) |
| **Soglia Hamming** | 10 | 0-64 | Distanza massima per keyframe match (0=identici, 64=qualsiasi) |
| **Match ratio** | 60% | 0-100% | % di frame che devono matchare per considerare il video un duplicato |

### Come Modificare le Impostazioni

1. **Via dialogo**: Clicca **IMPOSTAZIONI** → modifica i valori → clicca **OK**
2. **Ripristino rapido**: Usa il pulsante **Ripristina Default** all'interno della finestra **Impostazioni** per tornare ai default
3. **Nel dialogo**: Clicca **Ripristina Default** per tornare ai valori di fabbrica

Le impostazioni vengono salvate automaticamente in `video_settings.json`.

---

## 📁 Struttura di Output

### Durante l'Analisi
```
cartella_analizzata/
├── duplicati_certi/          ← Cartella dei duplicati MD5 (Fase 1)
│   ├── photo.jpg
│   ├── photo(1).jpg
│   └── video.mp4(1)
└── [file originali rimangono qui]
```

### Sessione di Lavoro
Una sessione completa viene salvata in `sessione_alfa.json`:
- Tutte le coppie trovate
- Tutte le decisioni prese
- Può essere riaperta in seguito per modificare decisioni

### Log Completo
Il file `analysis_log.txt` contiene un log dettagliato di:
- Phase 1: File MD5 analizzati, duplicati trovati
- Phase 2: Immagini elaborate, distanze pHash
- Phase 3: Video candidati, match trovati
- Errori e file saltati

---

## 📊 Interpretare i Risultati

### Score (Similarità)
- **100**: Identici (o quasi identici)
- **70-90**: Molto simili (possibili varianti minori)
- **40-70**: Moderatamente simili (potrebbero non essere duplicati)
- **0-40**: Leggermente simili (probabilmente diversi)

### Fase 1 (MD5)
I file spostati in `duplicati_certi/` sono **100% uguali byte per byte**. Puoi eliminarli senza dubbi.

### Fase 2 (pHash Immagini)
I risultati mostrano foto molto simili (stesso soggetto, angolo, condizioni di scatto). Review con le tue impostazioni di tolleranza.

### Fase 3 (Video)
Analizza con metodo ibrido:
- Video brevi (≤60s): Estrae frame a intervalli fissati (5%, 20%, 45%, 65%, 80%)
- Video lunghi (>60s): Rileva scene-change e confronta keyframe

---

## 🔧 Risoluzione Problemi

### "File corrotto/illeggibile" durante Fase 3
Il programma ha saltato un video perché corrotto o non decodificabile. ✅ Comportamento normale, il video viene ignorato.

### Fase 2 molto lenta
- Riduci il numero di file immagini (separali in sottocartelle)
- O aspetta: dipende dalla risoluzione e dal numero di foto

### Fase 3 con pochi video
Se ci sono pochi video candidate, il programma termina rapidamente. ✅ Non è un errore.

### Dimensioni barre di progresso diverse
- P1, P2, P3 hanno lunghezze diverse perché misurano cose diverse (file, immagini, video)
- Questo è corretto e atteso

---

## 💾 Salvataggio e Ripresa

### Auto-Save
Ogni decisione presa viene salvata automaticamente in `sessione_alfa.json`.

### Riapri Sessione Precedente
Alle prossime esecuzioni, la sessione precedente viene ricordata:
- Coppie già viste rimangono come decise
- Nuove coppie vengono aggiunte

### Report Finale
Alla chiusura, la console mostra un riepilogo:
- Totale file analizzati
- Duplicati certi trovati (MD5)
- Immagini simili trovate (pHash)
- Match video trovati
- Spazio risparmiato

---

## 🛡️ Precauzioni di Sicurezza

✅ **Il programma è sicuro:**
- Non elimina file automaticamente (solo tu decidi)
- MD5 duplicati vengono spostati in cartella (non cancellati subito) → puoi recuperarli
- Sessione salvata → puoi rivedere tutte le decisioni
- Log completo → traccia di tutto

⚠️ **Migliori pratiche:**
1. **Backup prima**: Fai un backup della cartella prima di analizzarla
2. **Review prima di agire**: Non premere bottoni velocemente
3. **Zoom su immagini**: Usa tasto `1/2/3` per ispezionare bene prima di decidere
4. **Mappa differenze**: Premi `4` per visualizzare overlay delle differenze

---

## 📝 Changelog Versione 2.0

- ✅ Support completo video con analisi keyframe ibrida
- ✅ 3 fasi di analisi indipendenti e parallele
- ✅ Impostazioni video configurabili e persistenti
- ✅ 3 barre di progresso colorate (P1 rosso, P2 blu, P3 arancione)
- ✅ Logging dettagliato in `analysis_log.txt`
- ✅ Ripristino default impostazioni con 1 clic
- ✅ Mappa differenze (4 per foto)
- ✅ UI completamente riorganizzata (status bar ingrandita + video ridotto)
- ✅ Bug fix: differenze map visualizzazione
- ✅ Bug fix: progress bar phase 1 raggiunge 100% correttamente

---

## 👤 Supporto

Per modifiche, bug report o funzionalità richieste, consultare:
- **Log file**: `analysis_log.txt` per diagnostica dettagliata
- **Sessione**: `sessione_alfa.json` per stato completo dell'analisi
- **Impostazioni**: `video_settings.json` per config salvate

---

**Image Similarity Suite 2.0** — Beta/RC Release
*Data: 2026-02-06*
