import sys, os, json, shutil, time, hashlib
from PySide6.QtWidgets import (QApplication, QMainWindow, QFileDialog, QVBoxLayout, 
                             QWidget, QPushButton, QScrollArea, QProgressBar, 
                             QHBoxLayout, QLabel, QFrame, QMessageBox, QComboBox, QDialog)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPointF
from PySide6.QtGui import QPixmap, QKeyEvent

# --- COSTANTI DI SISTEMA (Facilmente editabili) ---
BATCH_SIZE = 100  # Dimensione lotto per aggiornamento UI e riordinamento
PHASH_THRESHOLD = 12 # Sensibilità analisi visiva

# Importazioni dai moduli di progetto
from analyzer import AnalyzerEngine
from session_manager import MediaPair
from ui_components import ComparisonCard, VideoComparisonCard 

# Ottimizzazione OpenCV
import cv2
cv2.setUseOptimized(True)

class AnalysisWorker(QThread):
    phase1_done = Signal(dict)
    status_update = Signal(str)
    progress = Signal(int)
    progress_phase1 = Signal(int)        # Progress Phase 1: 0-100%
    progress_phase2 = Signal(int)        # Progress Phase 2: 0-100%
    progress_phase3 = Signal(int)        # Progress Phase 3: 0-100%
    pair_found = Signal(object)
    auto_record = Signal(dict)
    phase2_done = Signal()
    finished = Signal()

    def __init__(self, folder_path, video_settings=None):
        super().__init__()
        self.folder_path = folder_path
        self._abort = False
        self.video_settings = video_settings or {}
        # Log file per tracciare fase 2 e 3
        self.log_file = os.path.join(folder_path, "analysis_log.txt")
        self._init_log()

    def _init_log(self):
        """Inizializza il file di log."""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write("=== ANALYSIS LOG ===\n")
                f.write(f"Inizio analisi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Cartella: {self.folder_path}\n")
                f.write("=" * 50 + "\n\n")
        except Exception:
            pass

    def _log_event(self, phase, message):
        """Aggiunge un evento al log."""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{phase}] {message}\n")
        except Exception:
            pass

    def get_md5(self, fname):
        # Blindatura: Gestione file non accessibili o permessi negati
        try:
            hash_md5 = hashlib.md5()
            with open(fname, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except (PermissionError, OSError):
            return None

    def run(self):
        # --- FASE 1: MD5 ---
        self.status_update.emit("Scansione in corso (Fase 1/2)...")
        excluded_folders = {"duplicati_certi", "ELABORATE_SIMILI"}
        all_files = []
        
        # Blindatura accesso root
        if not os.path.exists(self.folder_path):
            self.status_update.emit("Errore: Cartella non trovata.")
            self.finished.emit()
            return

        video_exts = ('.mp4', '.mov', '.mkv', '.avi')
        img_exts = ('.png', '.jpg', '.jpeg', '.webp')

        for root, dirs, files in os.walk(self.folder_path):
            dirs[:] = [d for d in dirs if d not in excluded_folders]
            for f in files:
                if f == "sessione_alfa.json": continue
                if f.lower().endswith(img_exts + video_exts):
                    all_files.append(os.path.join(root, f))
        
        total_files = len(all_files)
        if total_files == 0:
            self.finished.emit()
            return

        md5_map = {}
        moved_count = 0
        remaining_images = []
        remaining_videos = []
        dup_folder = os.path.join(self.folder_path, "duplicati_certi")

        for i, f_path in enumerate(all_files):
            if self._abort: return
            
            # Aggiornamento UI controllato (BATCH_SIZE)
            if i % BATCH_SIZE == 0:
                prog_phase1 = int(((i + 1) / total_files) * 100)
                self.progress_phase1.emit(prog_phase1)
            
            # Blindatura: get_md5 gestisce internamente permessi e file corrotti
            f_md5 = self.get_md5(f_path)
            if f_md5 is None: continue 

            if f_md5 in md5_map:
                try:
                    if not os.path.exists(dup_folder): os.makedirs(dup_folder)
                    base_name = os.path.basename(f_path)
                    name_part, extension = os.path.splitext(base_name)
                    dest = os.path.join(dup_folder, base_name)
                    counter = 1
                    while os.path.exists(dest):
                        dest = os.path.join(dup_folder, f"{name_part}({counter}){extension}")
                        counter += 1
                    shutil.move(f_path, dest)
                    moved_count += 1
                    self.auto_record.emit({"file_a": md5_map[f_md5], "file_b": dest, "score": "MD5", "decision": "DUPLICATO_CERTO_MD5"})
                except: continue
            else:
                md5_map[f_md5] = f_path
                if f_path.lower().endswith(video_exts):
                    remaining_videos.append(f_path)
                else:
                    remaining_images.append(f_path)

        # Completiamo la progress bar di fase 1 al 100% per coerenza UX
        self.progress_phase1.emit(100)
        self.phase1_done.emit({"total": total_files, "moved": moved_count})
        
        # --- FASE 2: pHash per IMMAGINI ---
        self.status_update.emit("Analisi visiva profonda (Immagini)...")
        self._log_event("PHASE2_START", f"Inizio Phase 2: {len(remaining_images)} immagini da analizzare")
        hashes = {}
        total_rem = len(remaining_images)
        
        for i, f in enumerate(remaining_images):
            if self._abort: return
            
            try:
                # Blindatura pHash: saltiamo file che PIL/OpenCV non riescono a decodificare
                h = AnalyzerEngine.get_perceptual_data(f)
                if h is None: 
                    self._log_event("PHASE2_SKIP", f"Saltato (non decodificabile): {os.path.basename(f)}")
                    continue
                
                match_count = 0
                for path_ref, h_ref in hashes.items():
                    dist = h - h_ref
                    if dist < PHASH_THRESHOLD:
                        self.pair_found.emit(MediaPair(path_ref, f, dist))
                        self._log_event("PHASE2_MATCH", f"Match trovato: {os.path.basename(path_ref)} <-> {os.path.basename(f)} (dist={dist})")
                        match_count += 1
                
                hashes[f] = h
                if match_count == 0:
                    self._log_event("PHASE2_ANALYZE", f"Analizzato: {os.path.basename(f)} (hash={h})")
            except Exception as e:
                self._log_event("PHASE2_ERROR", f"Errore per {os.path.basename(f)}: {str(e)}")
                continue
            
            # Progress Phase 2: 0-100%
            prog_phase2 = int(((i + 1) / total_rem) * 100) if total_rem > 0 else 100
            self.progress_phase2.emit(prog_phase2)
        
        self._log_event("PHASE2_END", f"Fine Phase 2: totali immagini elaborate={len(hashes)}")
        self.status_update.emit(f"Phase 2 conclusa: {len(hashes)} immagini analizzate")
        # Notifica il MainThread che la Phase 2 è finita
        try:
            self.phase2_done.emit()
        except Exception:
            pass

        # --- FASE 3: Analisi video (leggera, pairwise) ---
        if remaining_videos:
            try:
                # Parallelizziamo i confronti video ma applichiamo filtri preliminari per ridurre O(N^2)
                from video_analyzer import VideoAnalyzer, is_candidate_pair
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import multiprocessing

                duration_tol = float(self.video_settings.get('duration_tol', 0.02))
                res_tol = float(self.video_settings.get('res_tol', 0.05))
                score_thr = float(self.video_settings.get('score_threshold', 0.6))
                max_workers = int(max(1, min(32, int(self.video_settings.get('max_workers', max(1, min(8, multiprocessing.cpu_count() or 2)))))))

                self._log_event("PHASE3_START", f"Inizio Phase 3: {len(remaining_videos)} video da analizzare")
                self._log_event("PHASE3_CONFIG", f"Filtri: duration_tol={duration_tol*100:.1f}%, res_tol={res_tol*100:.1f}%, score_thr={score_thr*100:.0f}%, max_workers={max_workers}")

                va = VideoAnalyzer(scene_threshold=self.video_settings.get('scene_threshold', 30),
                                   match_hamming_thresh=int(self.video_settings.get('match_hamming_thresh', 10)))

                self.status_update.emit("Analisi video in corso (filtri + parallela)...")
                nv = len(remaining_videos)

                # Costruiamo la lista di candidate pair dopo i filtri rapidi
                candidate_pairs = []
                screened_count = 0
                
                # Pre-filtra: rimuovi video corrotti o non leggibili
                valid_videos = []
                for video_path in remaining_videos:
                    try:
                        from video_analyzer import get_duration_and_fps
                        dur, fps = get_duration_and_fps(video_path)
                        if dur > 0 and fps > 0:
                            valid_videos.append(video_path)
                        else:
                            self._log_event("PHASE3_SKIP", f"Video invalido (dur={dur}, fps={fps}): {os.path.basename(video_path)}")
                    except Exception as e:
                        self._log_event("PHASE3_SKIP", f"Video corrotto/illeggibile: {os.path.basename(video_path)} ({str(e)[:50]})")
                
                nv_valid = len(valid_videos)
                self._log_event("PHASE3_VALIDATION", f"Video validi: {nv_valid}/{nv}")
                
                if nv_valid == 0:
                    self.status_update.emit("Nessun video valido per l'analisi.")
                    self._log_event("PHASE3_END", "Phase 3 completata: nessun video valido")
                    self.progress_phase3.emit(100)
                else:
                    remaining_videos = valid_videos
                
                    # Costruiamo la lista di candidate pair dopo i filtri rapidi
                    total_pairs_to_check = int(nv_valid * (nv_valid - 1) / 2) if nv_valid > 1 else 1
                    
                    for i in range(nv_valid):
                        if self._abort: break
                        a = remaining_videos[i]
                        for j in range(i + 1, nv_valid):
                            b = remaining_videos[j]
                            try:
                                if is_candidate_pair(a, b, duration_tol=duration_tol, res_tol=res_tol):
                                    candidate_pairs.append((a, b))
                                    self._log_event("PHASE3_CANDIDATE", f"Match criteri metadata: {os.path.basename(a)} <-> {os.path.basename(b)}")
                            except Exception as e:
                                self._log_event("PHASE3_CANDIDATE_ERROR", f"Errore screening: {os.path.basename(a)} vs {os.path.basename(b)}: {str(e)[:50]}")
                            screened_count += 1
                            # Progress Phase 3: Screening 0-20%
                            prog = int((screened_count / total_pairs_to_check) * 20) if total_pairs_to_check > 0 else 20
                            self.progress_phase3.emit(prog)
                            if screened_count % 100 == 0:
                                self.status_update.emit(f"Screening: {screened_count}/{total_pairs_to_check} coppie")

                total_candidates = len(candidate_pairs)
                self._log_event("PHASE3_SCREENING_DONE", f"Coppie candidate trovate: {total_candidates} su {int(nv * (nv - 1) / 2)}")
                
                if total_candidates == 0:
                    self.status_update.emit("Nessuna coppia candidata per i video.")
                    self._log_event("PHASE3_END", "Phase 3 completata: nessuna coppia da analizzare")
                else:
                    # Eseguiamo i confronti in parallelo con pool
                    with ThreadPoolExecutor(max_workers=max_workers) as ex:
                        futures = {ex.submit(va.compare_videos, a, b, [5,20,45,65,80], 60.0, self.video_settings.get('match_ratio_thresh', 0.6)): (a, b) for a, b in candidate_pairs}
                        completed = 0
                        matched_count = 0
                        
                        for fut in as_completed(futures):
                            if self._abort:
                                break
                            a, b = futures[fut]
                            try:
                                res = fut.result()
                                score = float(res.get('score', 0.0))
                                matched_frames = res.get('matched', 0)
                                total_frames = res.get('total', 0)
                                
                                if score >= score_thr:
                                    score_int = int(round(score * 100))
                                    self.pair_found.emit(MediaPair(a, b, score_int))
                                    matched_count += 1
                                    self._log_event("PHASE3_MATCH", f"Match video: {os.path.basename(a)} <-> {os.path.basename(b)} (score={score:.2f}, matched={matched_frames}/{total_frames})")
                                else:
                                    self._log_event("PHASE3_NO_MATCH", f"No match: {os.path.basename(a)} <-> {os.path.basename(b)} (score={score:.2f}, soglia={score_thr:.2f})")
                            except Exception as e:
                                self._log_event("PHASE3_ERROR", f"Errore compare {os.path.basename(a)} vs {os.path.basename(b)}: {str(e)[:100]}")
                                pass
                            
                            completed += 1
                            # Progress Phase 3: Comparisons 20-100%
                            prog = 20 + int((completed / total_candidates) * 80)
                            self.progress_phase3.emit(prog)
                    
                    self._log_event("PHASE3_END", f"Phase 3 completata: {matched_count} match su {total_candidates} coppie")
            except Exception as e:
                self._log_event("PHASE3_EXCEPTION", f"Errore critico Phase 3: {str(e)}")
                self.status_update.emit(f"Errore in Phase 3: {str(e)}")
        else:
            self._log_event("PHASE3_SKIPPED", "Phase 3 saltata: nessun video trovato")
            self.status_update.emit("Analisi completata (nessun video da analizzare).")

        self._log_event("MAIN", f"Analisi completata: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.status_update.emit("Analisi completata. File pronti per la revisione.")
        self.finished.emit()

# =============================================================================
# MAIN WINDOW: Il Centro di Comando
# =============================================================================
class MainWindow(QMainWindow):
    # Parametri Anti-Flickering
    BATCH_SIZE_TRIGGER = 100  
    INSERTION_SPEED_MS = 15   

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Similarity Suite - V2.0 (beta)")
        self.resize(1350, 950)
        
        self.current_folder = None
        self.active_card = None
        self.auto_duplicates = [] 
        self.all_pairs = []       
        self.pending_batch = []   

        # Impostazioni video configurabili dall'utente (valori di default - AMPLIATI PER TESTING)
        self.video_settings = {
            'duration_tol': 0.15,      # 15% (da 2%)
            'res_tol': 0.20,           # 20% (da 5%)
            'score_threshold': 0.35,   # 35% (da 60%)
            'max_workers': max(1, min(8, os.cpu_count() or 2)),
            'scene_threshold': 30,
            'match_hamming_thresh': 20, # 20 (da 10)
            'match_ratio_thresh': 0.35  # 35% (da 60%)
        }

        # percorso file impostazioni (persistenza tra esecuzioni)
        self._video_settings_file = os.path.join(os.path.dirname(__file__), "video_settings.json")
        self._load_video_settings()

        self.init_ui()
        # Aggiorna il banner delle impostazioni ora che la UI è inizializzata
        try:
            self.refresh_video_settings_display()
        except Exception:
            pass

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        
        # HEADER
        header = QHBoxLayout()
        self.btn_scan = QPushButton("NUOVA ANALISI")
        self.btn_scan.setMinimumHeight(40)
        self.btn_scan.clicked.connect(self.start_scan)
        
        self.combo_sort = QComboBox()
        self.combo_sort.setMinimumHeight(40)
        # Definiamo le voci in modo che contengano le parole chiave cercate dal metodo
        self.combo_sort.addItems(["Ordine: Arrivo", "Score: Crescente", "Score: Decrescente"])
        # Colleghiamo il segnale testuale
        self.combo_sort.currentTextChanged.connect(self.reorder_gallery)
        
        self.lbl_status = QLabel("Pronto")
        self.lbl_status.setStyleSheet("color: #2980b9; font-weight: bold; font-size: 14px;")
        
        # Progress bar Phase 1 (ROSSO - MD5)
        self.pbar_phase1 = QProgressBar()
        self.pbar_phase1.setFixedHeight(20)
        self.pbar_phase1.setStyleSheet("""
            QProgressBar { background-color: #ecf0f1; border: 1px solid #95a5a6; border-radius: 5px; }
            QProgressBar::chunk { background-color: #e74c3c; }
        """)
        self.pbar_phase1.hide()
        
        # Progress bar Phase 2 (BLU)
        self.pbar_phase2 = QProgressBar()
        self.pbar_phase2.setFixedHeight(20)
        self.pbar_phase2.setStyleSheet("""
            QProgressBar { background-color: #ecf0f1; border: 1px solid #95a5a6; border-radius: 5px; }
            QProgressBar::chunk { background-color: #3498db; }
        """)
        self.pbar_phase2.hide()
        
        # Progress bar Phase 3 (ARANCIONE)
        self.pbar_phase3 = QProgressBar()
        self.pbar_phase3.setFixedHeight(20)
        self.pbar_phase3.setStyleSheet("""
            QProgressBar { background-color: #ecf0f1; border: 1px solid #95a5a6; border-radius: 5px; }
            QProgressBar::chunk { background-color: #e67e22; }
        """)
        self.pbar_phase3.hide()
        
        self.btn_exit = QPushButton("SALVA ED ESCI")
        self.btn_exit.setMinimumHeight(40)
        self.btn_exit.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 0 20px;")
        self.btn_exit.clicked.connect(self.final_action_engine)

        # Pulsante per coppie video: permette di aggiungere manualmente coppie per revisione
        self.btn_add_video = QPushButton("AGGIUNGI COPPIA VIDEO")
        self.btn_add_video.setMinimumHeight(40)
        self.btn_add_video.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold; padding: 0 12px;")
        self.btn_add_video.clicked.connect(self.add_video_pair)

        # Pulsante impostazioni (generale)
        self.btn_video_settings = QPushButton("IMPOSTAZIONI")
        self.btn_video_settings.setMinimumHeight(40)
        self.btn_video_settings.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 0 12px;")
        self.btn_video_settings.clicked.connect(self.open_video_settings)

        header.addWidget(self.btn_scan)
        header.addWidget(self.combo_sort)
        header.addWidget(self.lbl_status)
        
        # Aggiungiamo label e progress bar per Phase 1
        lbl_p1 = QLabel("P1:")
        lbl_p1.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 11px;")
        header.addWidget(lbl_p1)
        header.addWidget(self.pbar_phase1, 1)
        
        # Aggiungiamo label e progress bar per Phase 2
        lbl_p2 = QLabel("P2:")
        lbl_p2.setStyleSheet("color: #3498db; font-weight: bold; font-size: 11px;")
        header.addWidget(lbl_p2)
        header.addWidget(self.pbar_phase2, 1)
        
        # Aggiungiamo label e progress bar per Phase 3
        lbl_p3 = QLabel("P3:")
        lbl_p3.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 11px;")
        header.addWidget(lbl_p3)
        header.addWidget(self.pbar_phase3, 1)
        
        header.addWidget(self.btn_video_settings)
        header.addWidget(self.btn_exit)
        self.main_layout.addLayout(header)

        # GALLERY
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #f0f0f0; border: none;")
        self.container = QWidget()
        self.gallery_layout = QVBoxLayout(self.container)
        self.gallery_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        self.main_layout.addWidget(self.scroll)

        # STATUS BAR PREMIUM (Confronto EXIF/Tecnico)
        self.status_panel = QFrame()
        self.status_panel.setFixedHeight(200)
        self.status_panel.setStyleSheet("background: white; border-top: 3px solid #e67e22;")
        s_layout = QHBoxLayout(self.status_panel)
        s_layout.setContentsMargins(20, 10, 20, 10)
        
        # AREA IMMAGINI (ingrandita)
        self.lbl_info_a = QLabel("Seleziona una coppia")
        self.lbl_stats = QLabel("<b>REPORT SESSIONE</b><br>---")
        self.lbl_stats.setAlignment(Qt.AlignCenter)
        self.lbl_stats.setStyleSheet("background: #f8f9fa; border-radius: 10px; padding: 10px; border: 1px solid #ddd;")
        self.lbl_info_b = QLabel("")
        
        for l in [self.lbl_info_a, self.lbl_info_b]: 
            l.setWordWrap(True)
            l.setStyleSheet("font-family: 'Segoe UI'; font-size: 13px;")
            
        s_layout.addWidget(self.lbl_info_a, 3)
        s_layout.addWidget(self.lbl_stats, 2)
        s_layout.addWidget(self.lbl_info_b, 3)

        # AREA VIDEO (ridotta con bottone e impostazioni)
        video_area = QVBoxLayout()
        video_area.setContentsMargins(5, 5, 5, 5)
        video_area.setSpacing(5)
        
        # Riga dei pulsanti: AGGIUNGI VIDEO e RESTORE DEFAULTS
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(3)
        
        self.btn_add_video = QPushButton("AGGIUNGI VIDEO")
        self.btn_add_video.setMinimumHeight(30)
        self.btn_add_video.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold; padding: 0 10px; font-size: 11px;")
        self.btn_add_video.clicked.connect(self.add_video_pair)
        buttons_row.addWidget(self.btn_add_video, 1)
        
        # Il pulsante di ripristino è ora presente nella finestra 'Impostazioni'
        
        video_area.addLayout(buttons_row)
        
        # Banner per mostrare le impostazioni video correnti in forma colonnare
        self.lbl_video_settings = QLabel("Impostazioni video: -")
        self.lbl_video_settings.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_video_settings.setStyleSheet("font-size:11px; color:#2c3e50; background:#fff3e0; border-radius:6px; padding:8px;")
        self.lbl_video_settings.setWordWrap(True)
        video_area.addWidget(self.lbl_video_settings, 1)
        
        video_frame = QFrame()
        video_frame.setLayout(video_area)
        s_layout.addWidget(video_frame, 1)

        self.main_layout.addWidget(self.status_panel)

    # --- CORE LOGIC ---

    def start_scan(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona cartella di lavoro")
        if not folder: return
        self.current_folder = folder
        self.auto_duplicates = []
        self.all_pairs = []
        self.clear_gallery()
        
        json_path = os.path.join(folder, "sessione_alfa.json")
        if os.path.exists(json_path):
            if QMessageBox.question(self, "Sessione Trovata", "Vuoi riprendere il lavoro precedente?") == QMessageBox.Yes:
                self.load_session(json_path)
                return

        # Mostra solo la progress bar relativa alla Phase 1 all'avvio
        self.pbar_phase1.show()
        self.pbar_phase2.hide()
        self.pbar_phase3.hide()
        self.worker = AnalysisWorker(folder, video_settings=self.video_settings)
        self.worker.status_update.connect(self.lbl_status.setText)
        self.worker.progress_phase1.connect(self.pbar_phase1.setValue)
        self.worker.progress_phase2.connect(self.pbar_phase2.setValue)
        self.worker.progress_phase3.connect(self.pbar_phase3.setValue)
        self.worker.auto_record.connect(lambda d: self.auto_duplicates.append(d))
        self.worker.phase1_done.connect(self.handle_phase1_report)
        # Collego handler per mostrare/nascondere le progress bar tra le fasi
        self.worker.phase1_done.connect(self._on_phase1_done)
        self.worker.phase2_done.connect(self._on_phase2_done)
        self.worker.pair_found.connect(self.enqueue_pair)
        self.worker.finished.connect(self.on_analysis_finished)
        self.worker.start()

    def _on_phase1_done(self, stats):
        """Nasconde la P1 e mostra la P2 quando la Phase 1 è completata."""
        try:
            self.pbar_phase1.hide()
            self.pbar_phase2.show()
            # assicurati che la barra di Phase2 sia azzerata all'inizio
            self.pbar_phase2.setValue(0)
        except Exception:
            pass

    def _on_phase2_done(self):
        """Nasconde la P2 e mostra la P3 quando la Phase 2 è completata."""
        try:
            self.pbar_phase2.hide()
            self.pbar_phase3.show()
            self.pbar_phase3.setValue(0)
        except Exception:
            pass

    def add_video_pair(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Seleziona almeno due video", filter="Video Files (*.mp4 *.mov *.mkv *.avi)")
        if not paths or len(paths) < 2:
            QMessageBox.information(self, "Selezione incompleta", "Seleziona almeno due file video.")
            return
        a, b = paths[0], paths[1]
        pair = MediaPair(a, b, 0)
        self.all_pairs.append(pair)
        card = VideoComparisonCard(pair, index=self.gallery_layout.count())
        self.gallery_layout.addWidget(card)
        self.refresh_global_stats()

    def open_video_settings(self):
        from ui_components import VideoSettingsDialog
        dlg = VideoSettingsDialog(self, settings=self.video_settings)
        if dlg.exec() == QDialog.Accepted:
            self.video_settings = dlg.get_settings()
            # Persistiamo le impostazioni su file
            try:
                self._save_video_settings()
                self.lbl_status.setText("Impostazioni video aggiornate e salvate.")
            except Exception as e:
                self.lbl_status.setText("Impostazioni aggiornate ma non salvate.")
                QMessageBox.warning(self, "Errore salvataggio", f"Impossibile salvare le impostazioni: {e}")            # Aggiorna il banner subito dopo il salvataggio
            try:
                self.refresh_video_settings_display()
            except Exception:
                pass
            # Applica la preferenza di ordinamento passata dal dialog
            try:
                sort_mode = self.video_settings.get('sort_mode')
                if sort_mode and sort_mode in ["Ordine: Arrivo", "Score: Crescente", "Score: Decrescente"]:
                    # Imposta la drop-down principale sul nuovo criterio
                    self.combo_sort.setCurrentText(sort_mode)
            except Exception:
                pass
            
            
        else:
            self.lbl_status.setText("Impostazioni video non modificate.")

    def restore_video_defaults(self):
        """Ripristina le impostazioni video ai valori di default."""
        from ui_components import VideoSettingsDialog
        self.video_settings = VideoSettingsDialog.DEFAULTS.copy()
        try:
            self._save_video_settings()
            self.refresh_video_settings_display()
            self.lbl_status.setText("Impostazioni video ripristinate ai default.")
            QMessageBox.information(self, "Impostazioni Ripristinate", "Le impostazioni video sono state ripristinate ai valori di default.")
        except Exception as e:
            self.lbl_status.setText("Errore nel ripristino delle impostazioni.")
            QMessageBox.warning(self, "Errore", f"Errore nel ripristino: {e}")
    
    def handle_phase1_report(self, stats):
        QMessageBox.information(self, "Fase 1: MD5 Completata", 
                                f"Scansione binaria terminata.\n\n"
                                f"File totali: {stats['total']}\n"
                                f"Duplicati identici (MD5) isolati: {stats['moved']}")

    def _load_video_settings(self):
        """Carica le impostazioni video da file, se presente."""
        try:
            if os.path.exists(self._video_settings_file):
                with open(self._video_settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.video_settings.update(data)
                    # Aggiorna banner se la UI è stata inizializzata
                    try:
                        if hasattr(self, 'lbl_video_settings'):
                            self.refresh_video_settings_display()
                        else:
                            self.lbl_status.setText("Impostazioni video caricate.")
                    except Exception:
                        pass
        except Exception as e:
            print(f"Impossibile caricare video_settings: {e}")

    def _save_video_settings(self):
        """Salva le impostazioni video sul file di configurazione locale."""
        with open(self._video_settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.video_settings, f, indent=2)


    def enqueue_pair(self, pair):
        self.all_pairs.append(pair)
        self.pending_batch.append(pair)
        if len(self.pending_batch) >= self.BATCH_SIZE_TRIGGER:
            self.flush_pending_batch()

    def flush_pending_batch(self):
        if not self.pending_batch: return
        batch = self.pending_batch[:]
        self.pending_batch = []
        self._process_batch_gradually(batch)

    def _process_batch_gradually(self, batch):
        """Gestisce l'inserimento a lotti e aggiorna il feedback visivo."""
        if not batch: 
            # --- RILASCIO STATO: Il sistema torna libero solo QUI ---
            self.refresh_global_stats()
            self.lbl_status.setText("✅ Analisi finita. Pronto per la revisione.")
            return
        
        # Estrazione lotto (Anti-Scattering)
        # Usiamo un chunk piccolo (5) per mantenere la UI fluida sulla workstation
        chunk_size = 5 
        chunk = batch[:chunk_size]
        remaining = batch[chunk_size:]
        
        curr_idx = self.gallery_layout.count()
        for i, p in enumerate(chunk):
            # Se la coppia è composta da video, usiamo VideoComparisonCard per una UI adeguata
            a_ext = os.path.splitext(p.path_a)[1].lower()
            b_ext = os.path.splitext(p.path_b)[1].lower()
            video_exts = ('.mp4', '.mov', '.mkv', '.avi')
            if a_ext in video_exts and b_ext in video_exts:
                card = VideoComparisonCard(p, index=(curr_idx + i))
            else:
                card = ComparisonCard(p, index=(curr_idx + i))
            self.gallery_layout.addWidget(card)
            
        # Feedback dinamico: Testo (Procedimento a lotti visibile)
        total = len(self.all_pairs)
        current = self.gallery_layout.count()
        prog = int((current / total) * 100) if total > 0 else 100
        
        self.lbl_status.setText(f"⏳ Ordinamento: {prog}% ({current}/{total}) - Non interrompere")

        # Pausa tecnica (Art. 8 - Invarianza comportamentale)
        QTimer.singleShot(self.INSERTION_SPEED_MS, lambda: self._process_batch_gradually(remaining))

    def load_session(self, path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            for item in data:
                if item['decision'] == "DUPLICATO_CERTO_MD5":
                    self.auto_duplicates.append(item)
                else:
                    pair = MediaPair(item['file_a'], item['file_b'], item['score'])
                    pair.decision = item['decision']
                    self.all_pairs.append(pair)
            self._process_batch_gradually(self.all_pairs[:])
        except Exception as e:
            QMessageBox.critical(self, "Errore Sessione", f"Impossibile leggere il JSON: {e}")


    def reorder_gallery(self, sort_mode):
        """
        Riordina le card nella galleria applicando la costante BATCH_SIZE 
        per mantenere la fluidità della UI durante lo spostamento dei widget.
        """
        if not hasattr(self, 'gallery_layout') or self.gallery_layout.count() == 0:
            return

        # Utilizzo del nome corretto presente nel tuo codice per lo stato
        self.lbl_stats.setText(f"<b>Riordinamento: {sort_mode}</b>")
        
        if "Arrivo" in sort_mode:
            return

        widgets = []
        for i in range(self.gallery_layout.count()):
            w = self.gallery_layout.itemAt(i).widget()
            if w:
                widgets.append(w)
            
        if "Decrescente" in sort_mode:
            widgets.sort(key=lambda x: x.pair.score, reverse=True)
        elif "Crescente" in sort_mode:
            widgets.sort(key=lambda x: x.pair.score)

        # Utilizzo del nome corretto 'self.scroll' come da tuo file main.py
        self.scroll.setUpdatesEnabled(False)
        try:
            for i, w in enumerate(widgets):
                self.gallery_layout.removeWidget(w)
                self.gallery_layout.addWidget(w)
                
                if (i + 1) % BATCH_SIZE == 0:
                    self.scroll.setUpdatesEnabled(True)
                    QApplication.processEvents()
                    self.scroll.setUpdatesEnabled(False)
        finally:
            self.scroll.setUpdatesEnabled(True)
        
        if widgets:
            widgets[0].setFocus()
            self.set_active_card(widgets[0])
    
    def clear_gallery(self):
        """Pulisce la gallery in modo sicuro prevenendo RuntimeError."""
        self.active_card = None 
        # Reset delle info pannello superiore per evitare riferimenti a widget distrutti
        self.lbl_info_a.setText("In attesa di selezione...")
        self.lbl_info_b.setText("")
        
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # Disconnessione e rimozione dal sistema di rendering Qt
                widget.setParent(None)
                widget.deleteLater()

    # --- ACTION ENGINE FINALE ---

    def final_action_engine(self):
        if not self.current_folder: return
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Salvataggio e Azione")
        msg.setText("Fase finale: consolidamento dati.")
        msg.setInformativeText("Cosa desideri fare prima di uscire?")
        
        btn_save = msg.addButton("Solo Salva JSON ed Esci", QMessageBox.AcceptRole)
        btn_move = msg.addButton("Sposta Elaborati ed Esci", QMessageBox.ActionRole)
        btn_cancel = msg.addButton("Annulla", QMessageBox.RejectRole)
        
        msg.exec()
        if msg.clickedButton() == btn_cancel: return
        
        # Generazione Report Finale (MD5 + Decisioni)
        results = self.auto_duplicates[:]
        for i in range(self.gallery_layout.count()):
            w = self.gallery_layout.itemAt(i).widget()
            if w:
                results.append({
                    "file_a": w.pair.path_a, "file_b": w.pair.path_b,
                    "score": w.pair.score, "decision": w.pair.decision
                })
            
        with open(os.path.join(self.current_folder, "sessione_alfa.json"), "w") as f:
            json.dump(results, f, indent=4)
            
        if msg.clickedButton() == btn_move:
            self.execute_physical_move(results)
            
        QApplication.quit()

    def execute_physical_move(self, data):
        dest_folder = os.path.join(self.current_folder, "ELABORATE_SIMILI")
        if not os.path.exists(dest_folder): os.makedirs(dest_folder)
        count = 0
        for item in data:
            d = item['decision']
            to_move = []
            if d == "KEEP_A": to_move.append(item['file_b'])
            elif d == "KEEP_B": to_move.append(item['file_a'])
            elif d == "DISCARD_BOTH": to_move.extend([item['file_a'], item['file_b']])
            
            for path in to_move:
                if os.path.exists(path):
                    try: 
                        # Logica di protezione sovrascrittura per nomi identici da cartelle diverse
                        base_name = os.path.basename(path)
                        name, ext = os.path.splitext(base_name)
                        final_dest = os.path.join(dest_folder, base_name)
                        counter = 1
                        while os.path.exists(final_dest):
                            final_dest = os.path.join(dest_folder, f"{name}({counter}){ext}")
                            counter += 1
                            
                        shutil.move(path, final_dest)
                        count += 1
                    except: pass
        QMessageBox.information(self, "Fine Lavoro", f"Operazione conclusa.\nSpostati {count} file in {dest_folder}")

    # --- UI UPDATES ---

    def set_active_card(self, card):
        if self.active_card: self.active_card.set_focus(False)
        self.active_card = card
        card.set_focus(True)
        self.update_technical_comparison(card.pair)

    def update_technical_comparison(self, pair):
        try:
            # Determina il tipo di file (VIDEO o FOTO)
            video_exts = ('.mp4', '.mov', '.mkv', '.avi')
            path_a_ext = os.path.splitext(pair.path_a)[1].lower()
            path_b_ext = os.path.splitext(pair.path_b)[1].lower()
            type_a = "VIDEO" if path_a_ext in video_exts else "FOTO"
            type_b = "VIDEO" if path_b_ext in video_exts else "FOTO"
            
            def info(p):
                st = os.stat(p)
                px = QPixmap(p)
                exif = AnalyzerEngine.get_exif_data(p)
                return {"name": os.path.basename(p), "w": px.width(), "h": px.height(), 
                        "tot": px.width()*px.height(), "size": st.st_size, 
                        "h_size": f"{st.st_size/1024/1024:.2f} MB",
                        "date": exif.get('DateTime', 'N/D'), "mod": exif.get('Model', 'N/D')}
            
            a, b = info(pair.path_a), info(pair.path_b)
            # Highlights arancioni per il "vincitore" di risoluzione
            win_a = "color:#e67e22;font-weight:bold;" if a['tot'] > b['tot'] else ""
            win_b = "color:#e67e22;font-weight:bold;" if b['tot'] > a['tot'] else ""
            
            self.lbl_info_a.setText(f"<b style='color:#2ecc71; font-size:15px;'>{type_a} A: {a['name']}</b><br>"
                                   f"Risoluzione: <span style='{win_a}'>{a['w']}x{a['h']}</span><br>"
                                   f"Peso: {a['h_size']}<br>Scatto: {a['date']}")
            
            self.lbl_info_b.setText(f"<div align='right'><b style='color:#3498db; font-size:15px;'>{type_b} B: {b['name']}</b><br>"
                                   f"Risoluzione: <span style='{win_b}'>{b['w']}x{b['h']}</span><br>"
                                   f"Peso: {b['h_size']}<br>Modello: {a['mod']}</div>")
        except: pass

    def refresh_global_stats(self):
        total = self.gallery_layout.count()
        decided = sum(1 for i in range(total) if self.gallery_layout.itemAt(i).widget().pair.decision != "PENDING")
        self.lbl_stats.setText(f"<b>REPORT SESSIONE</b><br><span style='font-size:20px; color:#e67e22;'>{decided} / {total}</span><br>Analizzate")

    def on_analysis_finished(self):
        self.flush_pending_batch()
        # Nascondi tutte le progress bar a fine analisi (P1 inclusa)
        self.pbar_phase1.hide()
        self.pbar_phase2.hide()
        self.pbar_phase3.hide()
        self.lbl_status.setText("Analisi Finita. Pronto per la revisione.")

    def refresh_video_settings_display(self):
        """Aggiorna il banner con le impostazioni correnti per il debug e il testing sul campo."""
        try:
            s = self.video_settings
            txt = (f"Video: dur {s.get('duration_tol',0.02)*100:.1f}% • res {s.get('res_tol',0.05)*100:.1f}% "
                   f"• score {s.get('score_threshold',0.6)*100:.0f}% • workers {s.get('max_workers',4)} • "
                   f"scene {s.get('scene_threshold',30)} • ham {s.get('match_hamming_thresh',10)} • "
                   f"match {s.get('match_ratio_thresh',0.6)*100:.0f}%")
            if hasattr(self, 'lbl_video_settings'):
                self.lbl_video_settings.setText(txt)
        except Exception:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())