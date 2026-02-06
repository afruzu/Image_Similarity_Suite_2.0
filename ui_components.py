import os
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu, QWidget, QMessageBox, QDialog, QFormLayout, QDoubleSpinBox, QSpinBox, QDialogButtonBox, QComboBox
from PySide6.QtGui import QPixmap, QCursor, QAction, QImage, QPainter, QColor, QPen, QFont
from PySide6.QtCore import Qt, QRect, QPoint, QPointF, QSize

class ComparisonCard(QFrame):
    # --- MATTONCINO: Colori Decisioni ---
    DECISION_COLORS = {
        "PENDING":     ("#dcdcdc", "#ffffff", "#000000"), 
        "KEEP_A":      ("#2ecc71", "#e8f8f5", "#000000"), 
        "KEEP_B":      ("#3498db", "#ebf5fb", "#000000"), 
        "DISCARD_BOTH":("#e74c3c", "#fdedec", "#ffffff"), 
        "DIFFERENT":   ("#9b59b6", "#f5eef8", "#ffffff"), 
    }

    def __init__(self, media_pair, index=0):
        super().__init__()
        # --- MATTONCINO: Stato e Dati ---
        self.pair = media_pair 
        self.index = index + 1 # Numero ordinale umano (parte da 1)
        self.zoom_factor = 1.0
        self.norm_offset = QPointF(0.0, 0.0) 
        self.is_panning = False
        self.last_mouse_pos = QPointF(0.0, 0.0)
        self.is_active = False

        # Configurazione Focus e Menu
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_zoom_menu)

        self.init_ui()   
        self.update_card_style()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        
        # --- RIMOSSO: Il numero fluttuante (lbl_index) che non si vedeva ---

        # --- Area Immagini ---
        self.container_img = QWidget()
        self.img_layout = QHBoxLayout(self.container_img)
        self.img_layout.setContentsMargins(0, 0, 0, 0)
        
        self.canvas_a = QLabel()
        self.canvas_b = QLabel()
        for c in [self.canvas_a, self.canvas_b]:
            c.setAlignment(Qt.AlignCenter)
            c.setMinimumSize(400, 400)
            c.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        
        self.img_layout.addWidget(self.canvas_a)
        self.img_layout.addWidget(self.canvas_b)
        self.main_layout.addWidget(self.container_img)

        # --- Barra Controlli Potenziata ---
        self.controls_layout = QHBoxLayout()
        
        # NUOVO BADGE: Ordinale + Score uniti e visibilissimi
        self.lbl_score = QLabel(f" #{self.index}  |  SCORE: {self.pair.score} ")
        self.lbl_score.setStyleSheet("""
            background-color: #2c3e50; 
            color: #f1c40f; 
            font-family: 'Segoe UI', sans-serif;
            font-size: 15px;
            font-weight: bold; 
            border-radius: 6px; 
            padding: 8px 15px;
            border: 2px solid #34495e;
        """)
        self.controls_layout.addWidget(self.lbl_score)
        self.controls_layout.addStretch() 
        
        self.is_diff_mode = False # Flag per tracciare lo stato della mappa differenze

        # Pulsanti RE-INGRANDITI
        self.btn_keep_a = QPushButton("TIENI A")
        self.btn_keep_b = QPushButton("TIENI B")
        self.btn_different = QPushButton("DIVERSE")
        self.btn_discard = QPushButton("ELIMINA")

        for btn_id, btn in [("KEEP_A", self.btn_keep_a), ("KEEP_B", self.btn_keep_b), 
                             ("DIFFERENT", self.btn_different), ("DISCARD_BOTH", self.btn_discard)]:
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(40)     # Più alti
            btn.setMinimumWidth(110)    # Più larghi come prima!
            btn.clicked.connect(lambda checked=False, d=btn_id: self.make_decision(d))
            self.controls_layout.addWidget(btn)
            
        self.main_layout.addLayout(self.controls_layout)
        self.refresh_previews()
        

    def update_card_style(self):
        """Aggiorna l'estetica basata su decisione e focus."""
        state = self.pair.decision
        sat_color, past_color, text_color = self.DECISION_COLORS[state]
        
        border_color = "#f1c40f" if self.is_active else sat_color
        border_width = "5px" if self.is_active else "2px"
        
        self.setStyleSheet(f"""
            ComparisonCard {{
                background-color: {past_color};
                border: {border_width} solid {border_color};
                border-radius: 12px;
            }}
            QPushButton {{
                background-color: white; border: 1px solid #bdc3c7; 
                border-radius: 4px; padding: 5px 15px; font-weight: bold;
            }}
        """)
        
        btns = [("KEEP_A", self.btn_keep_a), ("KEEP_B", self.btn_keep_b), 
                ("DIFFERENT", self.btn_different), ("DISCARD_BOTH", self.btn_discard)]
        for key, btn in btns:
            if key == state:
                btn.setStyleSheet(f"background-color: {sat_color}; color: {text_color}; border: 1px solid {sat_color};")
            else:
                btn.setStyleSheet("background-color: white; color: #2c3e50;")

    def keyPressEvent(self, event):
        """Scorciatoie: Zoom (1-3), Mappa (4), Reset (ESC/Spazio), Decisioni (A, B, D, E), Navigazione (Frecce)."""
        
        # --- Sezione Zoom e Reset ---
        if event.key() == Qt.Key_1: 
            self.set_zoom(1.0)
        elif event.key() == Qt.Key_2: 
            self.set_zoom(1.5)
        elif event.key() == Qt.Key_3: 
            self.set_zoom(999) 
        elif event.key() == Qt.Key_4: 
            self.show_diff_map()
        
        # --- NUOVI HOTKEY: Zoom Ciclico (+ e -) ---
        elif event.key() in [Qt.Key_Plus, Qt.Key_Equal]:
            self.cycle_view_mode(forward=True)
        elif event.key() == Qt.Key_Minus:
            self.cycle_view_mode(forward=False)

        elif event.key() in [Qt.Key_Escape, Qt.Key_Space]:
            self.set_zoom(1.0)
            self.norm_offset = QPointF(0, 0)
            self.refresh_previews()

        # --- Sezione Decisioni ---
        elif event.key() == Qt.Key_A:
            self.make_decision("KEEP_A")
        elif event.key() == Qt.Key_B:
            self.make_decision("KEEP_B")
        elif event.key() == Qt.Key_D:
            self.make_decision("DIFFERENT")
        elif event.key() == Qt.Key_E:
            self.make_decision("DISCARD_BOTH")

        # --- NUOVA SEZIONE: Navigazione Orizzontale (Frecce Sinistra/Destra) ---
        elif event.key() in [Qt.Key_Left, Qt.Key_Right]:
            main_win = self.window()
            # Verifichiamo che la MainWindow sia accessibile e abbia il layout
            if main_win and hasattr(main_win, 'gallery_layout'):
                layout = main_win.gallery_layout
                current_idx = layout.indexOf(self)
                
                # Calcoliamo il nuovo indice
                new_idx = current_idx - 1 if event.key() == Qt.Key_Left else current_idx + 1
                
                # Verifichiamo di non uscire dai bordi (0 ... N-1)
                if 0 <= new_idx < layout.count():
                    target_card = layout.itemAt(new_idx).widget()
                    if target_card:
                        # Spostiamo il focus e aggiorniamo la MainWindow
                        target_card.setFocus()
                        main_win.set_active_card(target_card)
                        # Allineamento automatico della scroll area
                        main_win.scroll.ensureWidgetVisible(target_card)
            event.accept()

        # --- Chiusura ---
        else:
            super().keyPressEvent(event)

    def cycle_view_mode(self, forward=True):
        """
        Gestisce la commutazione ciclica tra i 4 stati:
        FIT -> ZOOM -> PIXEL -> DIFF -> FIT ...
        usando stati simbolici per evitare problemi di float o valori magici.
        """

        # Definizione degli stati simbolici
        states = ["fit", "zoom", "pixel", "diff"]

        # Determinazione dello stato attuale
        if self.is_diff_mode:
            current_state = "diff"
        else:
            if self.zoom_factor == 1.0:
                current_state = "fit"
            elif self.zoom_factor == 1.5:
                current_state = "zoom"
            else:
                current_state = "pixel"

        # Calcolo del prossimo stato
        idx = states.index(current_state)
        if forward:
            next_state = states[(idx + 1) % len(states)]
        else:
            next_state = states[(idx - 1) % len(states)]

        # Applicazione del nuovo stato
        if next_state == "fit":
            self.set_zoom(1.0)
        elif next_state == "zoom":
            self.set_zoom(1.5)
        elif next_state == "pixel":
            self.set_zoom(999)
        elif next_state == "diff":
            self.show_diff_map()

    def set_zoom(self, factor):
        """
        Imposta lo zoom e resetta correttamente lo stato diff-map.
        """
        self.is_diff_mode = False
        self.zoom_factor = factor

        # Ripristino etichetta originale
        self.lbl_score.setText(f" #{self.index}  |  SCORE: {self.pair.score} ")

        self.refresh_previews()

    def refresh_previews(self):
        """Rendering a 3 stadi con Pan Sincronizzato."""
        if not os.path.exists(self.pair.path_a) or not os.path.exists(self.pair.path_b): return
            
        def render_canvas(path, mode):
            pixmap = QPixmap(path)
            src_w, src_h = pixmap.width(), pixmap.height()

            if mode <= 1.0:
                return pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            cx = src_w / 2 + (self.norm_offset.x() * src_w)
            cy = src_h / 2 + (self.norm_offset.y() * src_h)

            if mode == 1.5:
                crop_w, crop_h = src_w / 1.5, src_h / 1.5
            else: # 1:1 Pixel Reali
                crop_w, crop_h = 400, 400

            tx = max(0, min(int(cx - crop_w / 2), int(src_w - crop_w)))
            ty = max(0, min(int(cy - crop_h / 2), int(src_h - crop_h)))
            
            final_view = QPixmap(400, 400)
            final_view.fill(QColor("#1a1a1a"))
            
            painter = QPainter(final_view)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(QRect(0, 0, 400, 400), pixmap, QRect(tx, ty, int(crop_w), int(crop_h)))
            painter.end()
            return final_view

        p_a = render_canvas(self.pair.path_a, self.zoom_factor)
        p_b = render_canvas(self.pair.path_b, self.zoom_factor)

        # Overlay PIP
        if self.zoom_factor > 1.0:
            for p in [p_a, p_b]:
                painter = QPainter(p)
                painter.setBrush(QColor(230, 126, 34, 180))
                painter.setPen(Qt.NoPen)
                painter.drawRect(5, 5, 100, 25)
                painter.setPen(Qt.white)
                label = "150% ZOOM" if self.zoom_factor == 1.5 else "1:1 PIXELS"
                painter.drawText(QRect(5, 5, 100, 25), Qt.AlignCenter, label)
                painter.end()

        self.canvas_a.setPixmap(p_a); self.canvas_b.setPixmap(p_b)

    def mousePressEvent(self, event):
        self.setFocus()
        main_win = self.window()
        if hasattr(main_win, 'set_active_card'): main_win.set_active_card(self)
        if event.button() == Qt.LeftButton and self.zoom_factor > 1.0:
            self.is_panning = True
            self.last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_panning:
            curr_pos = event.position()
            delta = curr_pos - self.last_mouse_pos
            # Sensibilità dinamica per il Pan
            sens = 2.0 if self.zoom_factor == 1.5 else 5.0
            self.norm_offset -= QPointF((delta.x()/400.0)/sens, (delta.y()/400.0)/sens)
            
            limit = 0.48
            self.norm_offset.setX(max(-limit, min(limit, self.norm_offset.x())))
            self.norm_offset.setY(max(-limit, min(limit, self.norm_offset.y())))
            
            self.last_mouse_pos = curr_pos
            self.refresh_previews()

    def mouseReleaseEvent(self, event):
        self.is_panning = False
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def show_zoom_menu(self, pos):
        menu = QMenu()
        menu.addAction("Vista Intera (1)").triggered.connect(lambda: self.set_zoom(1.0))
        menu.addAction("Zoom 150% (2)").triggered.connect(lambda: self.set_zoom(1.5))
        menu.addAction("Pixel Reali 1:1 (3)").triggered.connect(lambda: self.set_zoom(999))
        menu.addSeparator()
        menu.addAction("Mappa Differenze (4)").triggered.connect(self.show_diff_map)
        menu.exec(QCursor.pos())

    def show_diff_map(self):
        """Genera e visualizza la mappa differenze impostando il flag di stato."""
        import cv2
        self.is_diff_mode = True
        try:
            img_a = cv2.imread(self.pair.path_a)
            img_b = cv2.imread(self.pair.path_b)
            if img_a is None or img_b is None: 
                print(f"[DIFF_MAP] Errore caricamento: img_a={img_a is not None}, img_b={img_b is not None}")
                self.is_diff_mode = False
                return
            
            # Resize img_b alle dimensioni di img_a
            img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))
            
            # Calcola differenza e converti a grayscale
            diff = cv2.absdiff(img_a, img_b)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # Copia i dati per evitare problemi di scope con NumPy
            gray_data = gray.tobytes()
            
            # Crea QImage dalla copia
            q_img = QImage(gray_data, gray.shape[1], gray.shape[0], gray.shape[1], QImage.Format_Grayscale8)
            pix = QPixmap.fromImage(q_img).scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.lbl_img_a.setPixmap(pix)
            self.lbl_img_b.setPixmap(pix)
            self.lbl_score.setText("<b style='color:red;'>MAPPA DIFFERENZE</b>")
        except Exception as e:
            print(f"[DIFF_MAP] Errore: {str(e)}")
            self.is_diff_mode = False

    def make_decision(self, decision_type):
        self.is_diff_mode = True
        self.pair.decision = "PENDING" if self.pair.decision == decision_type else decision_type
        self.update_card_style()
        main_win = self.window()
        if hasattr(main_win, 'refresh_global_stats'): main_win.refresh_global_stats()

    def set_focus(self, active):
        self.is_active = active
        self.update_card_style()


class VideoComparisonCard(QFrame):
    """Scheda per presentare e interagire con una coppia di file video.
    Offre: anteprime video (prima immagine), pulsante di analisi rapida (usa VideoAnalyzer),
    visualizzazione keyframes e le solite decisioni (TIENI A/B, DIVERSE, ELIMINA).
    """
    def __init__(self, media_pair, index=0):
        super().__init__()
        self.pair = media_pair
        self.index = index + 1
        self.is_active = False

        self.init_ui()
        self.update_card_style()

    def init_ui(self):
        from video_analyzer import VideoAnalyzer
        self.va = VideoAnalyzer()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # area preview video
        self.container_vid = QWidget()
        self.vid_layout = QHBoxLayout(self.container_vid)
        self.vid_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas_a = QLabel()
        self.canvas_b = QLabel()
        for c in [self.canvas_a, self.canvas_b]:
            c.setAlignment(Qt.AlignCenter)
            c.setMinimumSize(400, 220)
            c.setStyleSheet("background-color: #111111; border-radius: 4px;")

        self.vid_layout.addWidget(self.canvas_a)
        self.vid_layout.addWidget(self.canvas_b)
        self.main_layout.addWidget(self.container_vid)

        # controls
        self.controls_layout = QHBoxLayout()
        self.lbl_score = QLabel(f" #{self.index}  |  SCORE: {self.pair.score} ")
        self.lbl_score.setStyleSheet("background-color: #34495e; color: #f1c40f; font-weight: bold; padding: 8px 12px; border-radius:6px;")
        self.controls_layout.addWidget(self.lbl_score)
        self.controls_layout.addStretch()

        self.btn_analyze = QPushButton("ANALIZZA")
        self.btn_kf = QPushButton("KEYFRAMES")
        for btn in [self.btn_analyze, self.btn_kf]:
            btn.setMinimumHeight(36)
            btn.setCursor(Qt.PointingHandCursor)
            self.controls_layout.addWidget(btn)

        # decision buttons
        self.btn_keep_a = QPushButton("TIENI A")
        self.btn_keep_b = QPushButton("TIENI B")
        self.btn_different = QPushButton("DIVERSE")
        self.btn_discard = QPushButton("ELIMINA")

        for btn_id, btn in [("KEEP_A", self.btn_keep_a), ("KEEP_B", self.btn_keep_b), ("DIFFERENT", self.btn_different), ("DISCARD_BOTH", self.btn_discard)]:
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(36)
            btn.setMinimumWidth(100)
            btn.clicked.connect(lambda checked=False, d=btn_id: self.make_decision(d))
            self.controls_layout.addWidget(btn)

        self.main_layout.addLayout(self.controls_layout)

        # connect actions
        self.btn_analyze.clicked.connect(self.run_analysis)
        self.btn_kf.clicked.connect(self.show_keyframes_popup)

        self.refresh_previews()

    def get_video_thumbnail(self, path, time_sec: float = 0.0, w=400, h=220):
        try:
            import cv2
            cap = cv2.VideoCapture(path)
            if not cap.isOpened(): return None
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_no = max(int(round(time_sec * fps)), 0)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None: return None
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = QImage(frame.data, frame.shape[1], frame.shape[0], frame.strides[0], QImage.Format_RGB888)
            pix = QPixmap.fromImage(img).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            return pix
        except: return None

    def update_card_style(self):
        state = self.pair.decision
        sat_color, past_color, text_color = ComparisonCard.DECISION_COLORS.get(state, ("#dcdcdc", "#ffffff", "#000000"))
        border_color = "#f1c40f" if self.is_active else sat_color
        border_width = "5px" if self.is_active else "2px"
        self.setStyleSheet(f"""
            VideoComparisonCard {{
                background-color: {past_color};
                border: {border_width} solid {border_color};
                border-radius: 12px;
            }}
            QPushButton {{
                background-color: white; border: 1px solid #bdc3c7; border-radius: 4px; padding: 5px 10px; font-weight: bold;
            }}
        """)
        for key, btn in [("KEEP_A", self.btn_keep_a), ("KEEP_B", self.btn_keep_b), ("DIFFERENT", self.btn_different), ("DISCARD_BOTH", self.btn_discard)]:
            if key == state:
                btn.setStyleSheet(f"background-color: {sat_color}; color: {text_color}; border: 1px solid {sat_color};")
            else:
                btn.setStyleSheet("background-color: white; color: #2c3e50;")

    def refresh_previews(self):
        pa = self.get_video_thumbnail(self.pair.path_a, 0.5)
        pb = self.get_video_thumbnail(self.pair.path_b, 0.5)
        if pa: self.canvas_a.setPixmap(pa)
        if pb: self.canvas_b.setPixmap(pb)

    def run_analysis(self):
        try:
            main_win = self.window()
            settings = getattr(main_win, 'video_settings', None)
            if settings:
                from video_analyzer import VideoAnalyzer
                va = VideoAnalyzer(scene_threshold=settings.get('scene_threshold', 30),
                                   match_hamming_thresh=int(settings.get('match_hamming_thresh', 10)))
                res = va.compare_videos(self.pair.path_a, self.pair.path_b, match_ratio_thresh=settings.get('match_ratio_thresh', 0.6))
            else:
                res = self.va.compare_videos(self.pair.path_a, self.pair.path_b)

            score = int(round(res.get('score', 0.0) * 100))
            self.pair.score = score
            self.lbl_score.setText(f" #{self.index}  |  SCORE: {self.pair.score} ")

            # mostra una piccola finestra di dettagli
            txt = f"Risultato: {res.get('result')}\nScore: {res.get('score'):.2f}\nMatched: {res.get('matched')} / {res.get('total')}"
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Analisi Video")
            dlg.setText(txt)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Errore Analisi", str(e))

    def show_keyframes_popup(self):
        try:
            # Assicuriamo che la card corrente abbia il focus e sia attiva nella MainWindow
            try:
                self.setFocus()
                main_win = self.window()
                if main_win and hasattr(main_win, 'set_active_card'):
                    main_win.set_active_card(self)
                if main_win and hasattr(main_win, 'scroll'):
                    try:
                        main_win.scroll.ensureWidgetVisible(self)
                    except Exception:
                        pass
            except Exception:
                pass
            from video_analyzer import get_duration_and_fps
            kf_a = self.va.extract_percent_keyframes(self.pair.path_a)
            kf_b = self.va.extract_percent_keyframes(self.pair.path_b)
            w = QWidget()
            w.setWindowTitle("Keyframes")
            layout = QHBoxLayout(w)
            left = QVBoxLayout()
            right = QVBoxLayout()
            duration_a = get_duration_and_fps(self.pair.path_a)[0]
            duration_b = get_duration_and_fps(self.pair.path_b)[0]
            # Costruiamo liste ordinate di percentuali per A e B
            percents_a = [p for p, _ in sorted(kf_a.items())]
            percents_b = [p for p, _ in sorted(kf_b.items())]

            # Aggiungiamo e rendiamo cliccabili le miniature (aprono lo zoom sulla coppia relativa)
            for i, (p, h) in enumerate(sorted(kf_a.items())):
                lbl = QLabel(f"{p}%")
                img = QLabel()
                t = (p / 100.0) * duration_a
                pix = self.get_video_thumbnail(self.pair.path_a, t, 200, 120)
                if pix: img.setPixmap(pix)
                # bind click to open zoom at this index
                def make_handler(idx):
                    return lambda event: self._open_keyframes_zoom(percents_a, percents_b, duration_a, duration_b, start_index=idx)
                img.mousePressEvent = make_handler(i)
                left.addWidget(lbl); left.addWidget(img)

            for i, (p, h) in enumerate(sorted(kf_b.items())):
                lbl = QLabel(f"{p}%")
                img = QLabel()
                t = (p / 100.0) * duration_b
                pix = self.get_video_thumbnail(self.pair.path_b, t, 200, 120)
                if pix: img.setPixmap(pix)
                def make_handler_b(idx):
                    return lambda event: self._open_keyframes_zoom(percents_a, percents_b, duration_a, duration_b, start_index=idx)
                img.mousePressEvent = make_handler_b(i)
                right.addWidget(lbl); right.addWidget(img)
            layout.addLayout(left); layout.addLayout(right)

            # Pulsante per aprire la vista ingrandita (zoom navigabile)
            btn_row = QHBoxLayout()
            btn_zoom = QPushButton("Apri Zoom Coppia")
            btn_zoom.setMinimumHeight(36)
            btn_zoom.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")
            btn_zoom.clicked.connect(lambda: self._open_keyframes_zoom(percents_a, percents_b, duration_a, duration_b))
            btn_row.addStretch(); btn_row.addWidget(btn_zoom)
            layout.addLayout(btn_row)

            w.setLayout(layout)
            # Manteniamo il riferimento per evitare che la finestra venga GC
            self._last_kf_window = w
            w.show()
        except Exception as e:
            QMessageBox.critical(self, "Errore Keyframes", str(e))

    def make_decision(self, decision_type):
        self.pair.decision = "PENDING" if self.pair.decision == decision_type else decision_type
        self.update_card_style()
        main_win = self.window()
        if hasattr(main_win, 'refresh_global_stats'): main_win.refresh_global_stats()

    def _open_keyframes_zoom(self, percents_a, percents_b, dur_a, dur_b, start_index=0):
        dlg = KeyframesZoomDialog(self, self.pair.path_a, self.pair.path_b, percents_a, percents_b, dur_a, dur_b, self.get_video_thumbnail, start_index)
        dlg.exec()

    def set_focus(self, active):
        self.is_active = active
        self.update_card_style()

    def mousePressEvent(self, event):
        """Attiva il focus e il pannello info quando clicchi sulla scheda."""
        self.setFocus()
        main_win = self.window()
        if hasattr(main_win, 'set_active_card'):
            main_win.set_active_card(self)
        super().mousePressEvent(event)


class VideoSettingsDialog(QDialog):
    """Dialog per modificare le soglie e parametri dell'analisi video."""
    
    # Valori di default preferiti
    DEFAULTS = {
        'duration_tol': 0.02,      # 2%
        'res_tol': 0.05,           # 5%
        'score_threshold': 0.6,    # 60%
        'max_workers': 4,
        'scene_threshold': 30,
        'match_hamming_thresh': 10,
        'match_ratio_thresh': 0.6  # 60%
    }
    
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni Video")
        self.settings = settings or {}

        form = QFormLayout(self)

        # Duration tolerance (display percent)
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setSuffix(" %")
        self.duration_spin.setRange(0.0, 100.0)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setValue(self.settings.get('duration_tol', 0.02) * 100)
        form.addRow("Tolleranza durata:", self.duration_spin)

        # Resolution tolerance (percent)
        self.res_spin = QDoubleSpinBox()
        self.res_spin.setSuffix(" %")
        self.res_spin.setRange(0.0, 100.0)
        self.res_spin.setSingleStep(0.5)
        self.res_spin.setValue(self.settings.get('res_tol', 0.05) * 100)
        form.addRow("Tolleranza risoluzione:", self.res_spin)

        # Score threshold (percent)
        self.score_spin = QDoubleSpinBox()
        self.score_spin.setSuffix(" %")
        self.score_spin.setRange(0.0, 100.0)
        self.score_spin.setSingleStep(1.0)
        self.score_spin.setValue(self.settings.get('score_threshold', 0.6) * 100)
        form.addRow("Soglia score:", self.score_spin)

        # Max workers
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 64)
        self.workers_spin.setValue(int(self.settings.get('max_workers', 4)))
        form.addRow("Max worker:", self.workers_spin)

        # Scene threshold
        self.scene_spin = QSpinBox()
        self.scene_spin.setRange(0, 255)
        self.scene_spin.setValue(int(self.settings.get('scene_threshold', 30)))
        form.addRow("Soglia scene (diff media):", self.scene_spin)

        # Hamming threshold
        self.hamming_spin = QSpinBox()
        self.hamming_spin.setRange(0, 64)
        self.hamming_spin.setValue(int(self.settings.get('match_hamming_thresh', 10)))
        form.addRow("Soglia Hamming (frame):", self.hamming_spin)

        # Match ratio thresh
        self.match_ratio_spin = QDoubleSpinBox()
        self.match_ratio_spin.setSuffix(" %")
        self.match_ratio_spin.setRange(0.0, 100.0)
        self.match_ratio_spin.setSingleStep(1.0)
        self.match_ratio_spin.setValue(self.settings.get('match_ratio_thresh', self.DEFAULTS['match_ratio_thresh']) * 100)
        form.addRow("Match ratio richiesto:", self.match_ratio_spin)

        # Sort mode selection (user preference)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Ordine: Arrivo", "Score: Crescente", "Score: Decrescente"])
        # Imposta valore iniziale se presente nelle settings
        sort_init = self.settings.get('sort_mode', "Ordine: Arrivo")
        if sort_init in ["Ordine: Arrivo", "Score: Crescente", "Score: Decrescente"]:
            self.sort_combo.setCurrentText(sort_init)
        form.addRow("Ordine risultati:", self.sort_combo)

        # Buttons with Restore Defaults
        btn_restore = QPushButton("Ripristina Default")
        btn_restore.setStyleSheet("background-color: #95a5a6; color: white; font-weight: bold;")
        btn_restore.clicked.connect(self.restore_defaults)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_restore)
        btn_layout.addStretch()
        btn_layout.addWidget(buttons)
        
        form.addRow(btn_layout)

    def restore_defaults(self):
        """Ripristina tutti i valori ai default."""
        self.duration_spin.setValue(self.DEFAULTS['duration_tol'] * 100)
        self.res_spin.setValue(self.DEFAULTS['res_tol'] * 100)
        self.score_spin.setValue(self.DEFAULTS['score_threshold'] * 100)
        self.workers_spin.setValue(self.DEFAULTS['max_workers'])
        self.scene_spin.setValue(self.DEFAULTS['scene_threshold'])
        self.hamming_spin.setValue(self.DEFAULTS['match_hamming_thresh'])
        self.match_ratio_spin.setValue(self.DEFAULTS['match_ratio_thresh'] * 100)

    def get_settings(self):
        return {
            'duration_tol': max(0.0, min(1.0, self.duration_spin.value() / 100.0)),
            'res_tol': max(0.0, min(1.0, self.res_spin.value() / 100.0)),
            'score_threshold': max(0.0, min(1.0, self.score_spin.value() / 100.0)),
            'max_workers': int(self.workers_spin.value()),
            'scene_threshold': int(self.scene_spin.value()),
            'match_hamming_thresh': int(self.hamming_spin.value()),
            'match_ratio_thresh': max(0.0, min(1.0, self.match_ratio_spin.value() / 100.0))
            , 'sort_mode': self.sort_combo.currentText()
        }


class KeyframesZoomDialog(QDialog):
    """Dialog che mostra una coppia di keyframes ingrandita e permette
    di scorrere le coppie con gli hotkey Up/Down o con i bottoni Prev/Next.
    """
    def __init__(self, parent, path_a, path_b, percents_a, percents_b, dur_a, dur_b, thumbnail_fetcher, start_index=0):
        super().__init__(parent)
        self.setWindowTitle("Zoom Keyframes")
        self.path_a = path_a
        self.path_b = path_b
        self.percents_a = sorted(percents_a)
        self.percents_b = sorted(percents_b)
        self.dur_a = dur_a
        self.dur_b = dur_b
        self.fetch = thumbnail_fetcher
        self.index = max(0, start_index)

        self.init_ui()
        self.refresh()

    def init_ui(self):
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PySide6.QtCore import Qt

        layout = QVBoxLayout(self)
        self.info_lbl = QLabel("")
        self.info_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_lbl)

        imgs = QHBoxLayout()
        self.lbl_a = QLabel()
        self.lbl_b = QLabel()
        for l in (self.lbl_a, self.lbl_b):
            l.setMinimumSize(640, 400)
            l.setStyleSheet("background-color: #111; border: 1px solid #333;")
            l.setAlignment(Qt.AlignCenter)
        imgs.addWidget(self.lbl_a)
        imgs.addWidget(self.lbl_b)
        layout.addLayout(imgs)

        btns = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_next = QPushButton("Next ▶")
        self.btn_prev.clicked.connect(self.prev)
        self.btn_next.clicked.connect(self.next)
        btns.addStretch(); btns.addWidget(self.btn_prev); btns.addWidget(self.btn_next); btns.addStretch()
        layout.addLayout(btns)

    def keyPressEvent(self, event):
        from PySide6.QtCore import Qt
        if event.key() in (Qt.Key_Up, Qt.Key_Left):
            self.prev()
        elif event.key() in (Qt.Key_Down, Qt.Key_Right):
            self.next()
        else:
            super().keyPressEvent(event)

    def prev(self):
        if self.index > 0:
            self.index -= 1
            self.refresh()

    def next(self):
        max_len = max(len(self.percents_a), len(self.percents_b))
        if self.index < max_len - 1:
            self.index += 1
            self.refresh()

    def refresh(self):
        # Scegli percentuali correnti (se assenti prendi l'ultimo disponibile)
        ai = min(self.index, max(0, len(self.percents_a) - 1)) if self.percents_a else 0
        bi = min(self.index, max(0, len(self.percents_b) - 1)) if self.percents_b else 0
        pa = self.percents_a[ai] if self.percents_a else 0
        pb = self.percents_b[bi] if self.percents_b else 0

        # Calcola tempi
        ta = (pa / 100.0) * self.dur_a if self.dur_a else 0.0
        tb = (pb / 100.0) * self.dur_b if self.dur_b else 0.0

        pix_a = None
        pix_b = None
        try:
            pix_a = self.fetch(self.path_a, ta, 640, 400)
        except Exception:
            pix_a = None
        try:
            pix_b = self.fetch(self.path_b, tb, 640, 400)
        except Exception:
            pix_b = None

        if pix_a: self.lbl_a.setPixmap(pix_a)
        else: self.lbl_a.setText("Frame non disponibile")
        if pix_b: self.lbl_b.setPixmap(pix_b)
        else: self.lbl_b.setText("Frame non disponibile")

        total = max(len(self.percents_a), len(self.percents_b), 1)
        self.info_lbl.setText(f"Coppia {self.index+1}/{total} — A: {pa}%  |  B: {pb}%")