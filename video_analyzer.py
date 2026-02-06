"""video_analyzer.py

Analisi di duplicati e similitudini per file video.

Funzionalità principali:
- identificazione duplicati esatti via MD5 + size + estensione
- estrazione keyframes percent-based e ricerca di cambi scena (semplice)
- hashing dei fotogrammi (aHash) e confronto via Hamming
- pipeline `compare_videos` che restituisce score e dettagli

Note: richiede OpenCV (cv2). ffprobe/ffmpeg opzionali ma utili per metadati più accurati.
"""

from __future__ import annotations

import os
import math
import json
import hashlib
import tempfile
from typing import List, Tuple, Dict, Optional

# Lazy import di cv2 - evita errore al module load time
cv2 = None
np = None

def _ensure_cv2():
    """Assicura che cv2 e numpy siano disponibili."""
    global cv2, np
    if cv2 is None or np is None:
        try:
            import cv2 as cv2_module
            import numpy as np_module
            cv2 = cv2_module
            np = np_module
            cv2.setLogLevel(0)  # Disabilita logging ffmpeg
            return True
        except ImportError as e:
            raise RuntimeError("OpenCV (cv2) è richiesto: pip install opencv-python") from e
    return True

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".video_fingerprints")
os.makedirs(CACHE_DIR, exist_ok=True)


def compute_md5(path: str, block_size: int = 65536) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
    return h.hexdigest()


def is_exact_duplicate(a: str, b: str) -> bool:
    if not os.path.exists(a) or not os.path.exists(b):
        return False
    if os.path.splitext(a)[1].lower() != os.path.splitext(b)[1].lower():
        return False
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    return compute_md5(a) == compute_md5(b)


def get_duration_and_fps(path: str) -> Tuple[float, float]:
    _ensure_cv2()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossibile aprire il file video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    duration = frame_count / fps if fps > 0 else 0.0
    return duration, fps


def get_video_resolution(path: str) -> Tuple[int, int]:
    """Restituisce (width, height) del video, o (0,0) se non disponibile."""
    _ensure_cv2()
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return 0, 0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        return w, h
    except Exception:
        return 0, 0


def is_candidate_pair(a: str, b: str, duration_tol: float = 0.02, res_tol: float = 0.05) -> bool:
    """Verifica rapidamente se due video sono candidati a confronto dettagliato.

    - duration_tol: tolleranza relativa (es. 0.02 = 2%)
    - res_tol: tolleranza relativa sulla dimensione (es. 0.05 = 5%)
    """
    try:
        da, _ = get_duration_and_fps(a)
        db, _ = get_duration_and_fps(b)
        if da <= 0 or db <= 0:
            return True  # non possiamo escludere - fallback permissivo
        if abs(da - db) / max(da, db) > duration_tol:
            return False

        wa, ha = get_video_resolution(a)
        wb, hb = get_video_resolution(b)
        if wa <= 0 or wb <= 0:
            return True
        # confronto risoluzione: verifica differenza relativa su larghezza e altezza
        if abs(wa - wb) / max(wa, wb) > res_tol:
            return False
        if abs(ha - hb) / max(ha, hb) > res_tol:
            return False

        return True
    except Exception:
        return True


def _get_frame_at_time(path: str, time_sec: float, prefer_bgr: bool = True) -> Optional[np.ndarray]:
    _ensure_cv2()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_no = max(int(round(time_sec * fps)), 0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    return frame if prefer_bgr else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def average_hash(image: np.ndarray, hash_size: int = 8) -> int:
    # image expected BGR or grayscale
    if image is None:
        raise ValueError("Image is None")
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    avg = resized.mean()
    diff = resized > avg
    # convert binary array to int
    bit_string = 0
    for v in diff.flatten():
        bit_string = (bit_string << 1) | int(v)
    return bit_string


def hamming_distance(h1: int, h2: int) -> int:
    return (h1 ^ h2).bit_count()


def _cache_path_for_file(path: str) -> str:
    md5 = compute_md5(path)
    return os.path.join(CACHE_DIR, f"{md5}.json")


def save_fingerprint_cache(path: str, data: Dict) -> None:
    with open(_cache_path_for_file(path), "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_fingerprint_cache(path: str) -> Optional[Dict]:
    p = _cache_path_for_file(path)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


class VideoAnalyzer:
    def __init__(self, scene_threshold: float = 30.0, frame_hash_size: int = 8, match_hamming_thresh: int = 10):
        self.scene_threshold = scene_threshold
        self.frame_hash_size = frame_hash_size
        self.match_hamming_thresh = match_hamming_thresh

    def extract_percent_keyframes(self, path: str, percents: List[float] = [5, 20, 45, 65, 80]) -> Dict[float, int]:
        _ensure_cv2()
        """Estrae keyframes alle percentuali fornite e ritorna una mappa percent->hash
        Usa come fallback frame al tempo esatto della percentuale.
        """
        duration, fps = get_duration_and_fps(path)
        result: Dict[float, int] = {}
        for p in percents:
            t = max(0.0, duration * (p / 100.0))
            frame = _get_frame_at_time(path, t)
            if frame is None:
                continue
            result[p] = average_hash(frame, self.frame_hash_size)
        return result

    def detect_scene_changes_simple(self, path: str, sample_interval: float = 1.0) -> List[float]:
        _ensure_cv2()
        """Rileva cambi scena campionando ogni sample_interval secondi e misurando differenza media.
        Restituisce i timestamps dove la differenza supera scene_threshold.
        """
        duration, fps = get_duration_and_fps(path)
        times = [i * sample_interval for i in range(0, max(1, int(duration // sample_interval)) + 1)]
        prev_frame = None
        changes: List[float] = []
        for t in times:
            frame = _get_frame_at_time(path, t, prefer_bgr=False)
            if frame is None:
                continue
            small = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_AREA)
            if prev_frame is not None:
                diff = cv2.absdiff(small, prev_frame)
                mean_diff = float(diff.mean())
                if mean_diff >= self.scene_threshold:
                    changes.append(t)
            prev_frame = small
        return changes

    def find_variable_keyframes(self, path: str, percents: List[float] = [5, 20, 45, 65, 80], search_window_sec: float = 3.0, step_sec: float = 0.5) -> Dict[float, int]:
        """Per ogni posizione percentuale cerca il primo cambiamento di scena all'interno di una finestra.
        Se non trova un cambio scena, usa il frame al tempo percentuale.
        """
        duration, fps = get_duration_and_fps(path)
        result: Dict[float, int] = {}
        for p in percents:
            anchor = max(0.0, duration * (p / 100.0))
            end = min(duration, anchor + search_window_sec)
            prev_frame = _get_frame_at_time(path, max(0.0, anchor - step_sec), anchor is not None)
            found = False
            t = anchor
            while t <= end:
                frame = _get_frame_at_time(path, t)
                if frame is None:
                    t += step_sec
                    continue
                # compare small grayscale difference
                gcurr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gcurr_s = cv2.resize(gcurr, (64, 64), interpolation=cv2.INTER_AREA)
                if prev_frame is not None:
                    gprev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
                    gprev_s = cv2.resize(gprev, (64, 64), interpolation=cv2.INTER_AREA)
                    diff = cv2.absdiff(gcurr_s, gprev_s)
                    if float(diff.mean()) >= self.scene_threshold:
                        # treat gcurr as keyframe
                        result[p] = average_hash(frame, self.frame_hash_size)
                        found = True
                        break
                prev_frame = frame
                t += step_sec
            if not found:
                frame = _get_frame_at_time(path, anchor)
                if frame is not None:
                    result[p] = average_hash(frame, self.frame_hash_size)
        return result

    def compare_videos(self, a: str, b: str, percent_positions: List[float] = [5, 20, 45, 65, 80], duration_cutoff: float = 60.0, match_ratio_thresh: float = 0.6) -> Dict:
        _ensure_cv2()
        """Confronta due video. Restituisce un dict con esito, score e dettagli.

        Strategia:
        - se duplicati esatti -> duplicato
        - altrimenti:
          - se entrambi <= duration_cutoff sec -> percent-based sampling
          - se uno o entrambi > duration_cutoff -> per ogni percent pos cerca primo cambio scena
        - confronta i frame hash per le posizioni corrispondenti e valuta percentuale di match
        """
        import os
        
        if is_exact_duplicate(a, b):
            return {"result": "duplicate", "score": 1.0, "details": "md5/size match"}

        duration_a, _ = get_duration_and_fps(a)
        duration_b, _ = get_duration_and_fps(b)

        use_scene = (duration_a > duration_cutoff) or (duration_b > duration_cutoff)
        
        if use_scene:
            fa = self.find_variable_keyframes(a, percent_positions)
            fb = self.find_variable_keyframes(b, percent_positions)
        else:
            fa = self.extract_percent_keyframes(a, percent_positions)
            fb = self.extract_percent_keyframes(b, percent_positions)

        # compare hashes
        matched = 0
        total = 0
        details = []
        for p in sorted(set(list(fa.keys()) + list(fb.keys()))):
            ha = fa.get(p)
            hb = fb.get(p)
            if ha is None or hb is None:
                continue
            total += 1
            hd = hamming_distance(ha, hb)
            matched_flag = hd <= self.match_hamming_thresh
            details.append({"percent": p, "hamming": hd, "match": matched_flag})
            if matched_flag:
                matched += 1

        score = (matched / total) if total > 0 else 0.0
        result = "similar" if score >= match_ratio_thresh else "different"
        return {"result": result, "score": score, "matched": matched, "total": total, "details": details}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="VideoAnalyzer quick CLI")
    parser.add_argument("action", choices=["compare", "rate"], help="action")
    parser.add_argument("a", help="video A")
    parser.add_argument("b", nargs="?", help="video B (for compare)")
    args = parser.parse_args()

    va = VideoAnalyzer()
    if args.action == "compare":
        if not args.b:
            parser.error("compare requires two videos")
        res = va.compare_videos(args.a, args.b)
        print(json.dumps(res, indent=2))
    elif args.action == "rate":
        print("Duration and fps for", args.a, get_duration_and_fps(args.a))
