class MediaPair:
    """Rappresenta una coppia di immagini simili con relativa decisione dell'utente."""
    def __init__(self, path_a, path_b, score):
        self.path_a = path_a
        self.path_b = path_b
        self.score = int(score)
        self.decision = "PENDING"

class SessionData:
    """Gestore centrale della sessione di analisi."""
    def __init__(self):
        self.pairs = []  # Lista di oggetti MediaPair
        self.binary_clones = {} # Per raggruppare MD5 identici

    def add_match(self, path_a, path_b, score):
        """Aggiunge una nuova coppia sospetta alla sessione."""
        self.pairs.append(MediaPair(path_a, path_b, score))
        