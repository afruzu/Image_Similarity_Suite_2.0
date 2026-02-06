"""Test di base per alcune utilità in video_analyzer.py"""

from video_analyzer import average_hash, hamming_distance
import numpy as np
import cv2


def make_test_image(value: int, size=(8, 8)):
    # crea un'immagine grayscale costante
    img = np.full((size[0], size[1]), value, dtype=np.uint8)
    return img


def test_average_hash_and_hamming():
    img1 = make_test_image(10)
    img2 = make_test_image(200)
    h1 = average_hash(img1, hash_size=8)
    h2 = average_hash(img2, hash_size=8)
    assert isinstance(h1, int)
    assert isinstance(h2, int)
    # immagini molto diverse dovrebbero avere hamming > 0
    assert hamming_distance(h1, h2) > 0


if __name__ == '__main__':
    test_average_hash_and_hamming()
    print('test OK')