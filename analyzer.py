import os
import cv2
import hashlib
import imagehash
from PIL import Image
from PIL.ExifTags import TAGS
import numpy as np

class AnalyzerEngine:
    """
    Il cuore pulsante del programma: implementa i 4 livelli di analisi.
    """

    @staticmethod
    def get_binary_hash(path):
        """Livello 0: Filtro di Ferro (Identità Binaria)."""
        # Usiamo un hash veloce per i duplicati esatti [cite: 36, 38]
        with open(path, "rb") as f:
            return hashlib.md5(f.read(65536)).hexdigest()

    @staticmethod
    def get_perceptual_data(path):
        """Livello 1: pHash (Similitudine Strutturale)."""
        # Basato sulla DCT, ignora compressione e piccoli ridimensionamenti [cite: 17, 31]
        img = Image.open(path)
        return imagehash.phash(img)

    @staticmethod
    def compute_diff_map(img_a, img_b):
        """Livello 2: Mappa delle Differenze (Analisi Visiva)."""
        # Sottrazione dei pixel per evidenziare i cambiamenti [cite: 78, 85]
        # Assumiamo img_a e img_b già caricati in RAM come array NumPy
        diff = cv2.absdiff(img_a, img_b)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        return thresh

    @staticmethod
    def get_feature_matches(img_a, img_b):
        """Livello 3: Tracking dei Punti Chiave (ORB)."""
        # Identifica dettagli specifici come occhi o bordi [cite: 59, 81]
        orb = cv2.ORB_create(nfeatures=500)
        kp1, des1 = orb.detectAndCompute(img_a, None)
        kp2, des2 = orb.detectAndCompute(img_b, None)
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        return matches, len(matches) # Restituisce i punti comuni [cite: 83, 86]
    

    @staticmethod
    def get_exif_data(path):
        
        info = {"DateTime": "Senza Data", "Model": "Camera Sconosciuta", "Size": "0x0", "Filesize": "0MB"}
        try:
            info["Filesize"] = f"{os.path.getsize(path) / (1024*1024):.2f} MB"
            with Image.open(path) as img:
                info["Size"] = f"{img.width}x{img.height}"
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        decoded = TAGS.get(tag, tag)
                        if decoded == "DateTimeOriginal": info["DateTime"] = value
                        if decoded == "Model": info["Model"] = value
        except Exception:
            pass
        return info